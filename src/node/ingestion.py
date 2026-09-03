import asyncio
import logging
from asyncio import CancelledError, create_task
from collections import OrderedDict
from contextlib import asynccontextmanager
from itertools import batched
from typing import TYPE_CHECKING, AsyncGenerator, List

from models.block import Block
from models.header.uncle import UncleHeader
from node.api.http import BlockEvent

if TYPE_CHECKING:
    from starlette.applications import Starlette

logger = logging.getLogger(__name__)

# Safe insert size for SQLite ^3.32.0
SQLITE_BATCH_INSERT_SIZE = 10_000

RETRY_INITIAL_SECONDS = 1.0
RETRY_MAX_SECONDS = 60.0


async def sync_to_node_tip(app: "Starlette") -> None:
    """
    Fetch the node's chain state and store its chain up to the tip, walking parent links
    backwards from the tip (which handles pruned/missing blocks), then flag that chain
    canonical. Retries indefinitely with exponential backoff on failure.
    """
    delay = RETRY_INITIAL_SECONDS

    while True:
        try:
            info = await app.state.node_api.get_info()
            logger.info(f"Node info: LIB={info.lib}, tip={info.tip}, slot={info.slot}, height={info.height}")
            app.state.lib_slot = info.lib_slot

            await backfill_chain_from_hash(app, info.tip)
            await follow_node_tip(app, bytes.fromhex(info.tip))
            return

        except Exception as error:
            logger.exception(f"Error during initial sync to the node's tip: {error}")
            logger.info(f"Retrying in {delay:.0f}s...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, RETRY_MAX_SECONDS)


async def follow_node_tip(app: "Starlette", tip: bytes) -> None:
    """Make the node's reported tip the canonical chain, fetching it first if it is missing."""
    db = app.state.db
    if db.block_by_hash(tip) is None:
        await backfill_chain_from_hash(app, tip.hex())
        if db.block_by_hash(tip) is None:
            logger.warning(f"Node tip {tip.hex()[:16]}... could not be fetched; canonical chain left unchanged")
            return
    if db.set_canonical_tip(tip):
        await app.state.notifier.publish()


async def backfill_chain_from_hash(app: "Starlette", block_hash: str) -> None:
    """
    Walk the chain backwards from block_hash until a stored block or genesis, then
    insert the missing blocks oldest-first in batches.

    Memory stays bounded on a long walk: only the hashes are kept for the whole
    chain, plus the bodies of the last SQLITE_BATCH_INSERT_SIZE blocks walked
    (which are the oldest, so the first batch needs no refetch). Older batches
    are fetched again when their turn comes.
    """
    node_api = app.state.node_api
    hashes: List[str] = []  # newest -> oldest
    recent_bodies: OrderedDict[str, Block] = OrderedDict()
    current_hash = block_hash

    while True:
        if app.state.db.block_by_hash(bytes.fromhex(current_hash)) is not None:
            logger.debug(f"Block {current_hash[:16]}... already exists, stopping chain walk")
            break

        block_serializer = await node_api.get_block_by_hash(current_hash)
        if block_serializer is None:
            logger.info(f"Block {current_hash[:16]}... not found on node (likely genesis parent), stopping chain walk")
            break

        block = block_serializer.into_block()
        hashes.append(current_hash)
        recent_bodies[current_hash] = block
        if len(recent_bodies) > SQLITE_BATCH_INSERT_SIZE:
            recent_bodies.popitem(last=False)

        current_hash = block.parent_block.hex()

    if not hashes:
        logger.info("No new blocks to backfill")
        return

    hashes.reverse()  # oldest -> newest, so parents are inserted before children
    for idx, chunk in enumerate(batched(hashes, SQLITE_BATCH_INSERT_SIZE)):
        blocks: List[Block] = []
        for chunk_hash in chunk:
            block = recent_bodies.pop(chunk_hash, None)
            if block is None:
                block_serializer = await node_api.get_block_by_hash(chunk_hash)
                if block_serializer is None:
                    raise RuntimeError(f"Block {chunk_hash[:16]}... disappeared from the node during backfill")
                block = block_serializer.into_block()
            blocks.append(block)

        # Only the oldest batch may start a chain root (its parent is genesis or pruned).
        app.state.db.store_blocks(blocks, allow_chain_root=(idx == 0))
        logger.info(f"Backfilled {len(blocks)} blocks (slots {blocks[0].slot} to {blocks[-1].slot})")
        await backfill_missing_uncles(app, [uncle for block in blocks for uncle in block.uncles])


# Uncle availability probes are independent reads, so they run concurrently.
UNCLE_FETCH_CONCURRENCY = 16


async def backfill_missing_uncles(app: "Starlette", uncles: List[UncleHeader]) -> None:
    """Fetch and store referenced uncle blocks the explorer does not have.

    The chain walk only visits canonical blocks, so uncles are missing unless
    the live stream delivered them. The node prunes non-canonical blocks once
    the LIB passes them, so only uncles at or above the LIB slot are asked for;
    the rest are gone for good. Uncles can chain, so a stored uncle's own
    missing ancestors and uncles are fetched too. Uncles are older than the
    block referencing them, so storing them never moves the canonical tip.
    """
    db = app.state.db
    lib_slot = getattr(app.state, "lib_slot", 0)
    candidates = {uncle.hash: uncle for uncle in uncles if uncle.slot >= lib_slot}
    missing = [h for h in candidates if db.block_by_hash(h) is None]

    for start in range(0, len(missing), UNCLE_FETCH_CONCURRENCY):
        chunk = missing[start : start + UNCLE_FETCH_CONCURRENCY]
        fetched = await asyncio.gather(*(app.state.node_api.get_block_by_hash(h.hex()) for h in chunk))
        # Inserts stay sequential: SQLite has a single writer and uncles may chain.
        for uncle_hash, block_serializer in zip(chunk, fetched):
            if block_serializer is None:
                logger.debug(f"Uncle {uncle_hash.hex()[:16]}... already pruned by the node; skipping")
                continue
            if db.block_by_hash(uncle_hash) is not None:
                continue  # stored meanwhile as an ancestor of another uncle
            block = block_serializer.into_block()
            if db.block_by_hash(block.parent_block) is None:
                await backfill_chain_from_hash(app, block.parent_block.hex())
            db.store_blocks([block])
            logger.debug(f"Stored uncle block at slot {block.slot}")
            await backfill_missing_uncles(app, block.uncles)


@asynccontextmanager
async def run_ingestion(app: "Starlette") -> AsyncGenerator[None]:
    """Sync to the node's tip, then follow its block stream until the app shuts down.

    Expects `app.state.db`, `app.state.node_api` and `app.state.notifier`.
    """
    await sync_to_node_tip(app)
    subscription = create_task(subscribe_to_new_blocks(app))
    try:
        yield
    finally:
        # The ingestion loop blocks on the node's block stream, so shutdown has
        # to cancel it explicitly or the process never exits on SIGTERM.
        subscription.cancel()
        try:
            await subscription
        except CancelledError:
            pass


async def subscribe_to_new_blocks(app: "Starlette") -> None:
    """Follow the node's block stream forever, reconnecting with backoff when it drops.

    A stream ends when the node restarts or the connection breaks; without a
    reconnect the explorer would silently stop updating while its health check
    still passed. Blocks missed while disconnected are recovered by the
    parent-missing backfill in `store_streamed_block`.
    """
    logger.info("Subscription to new blocks started.")
    delay = RETRY_INITIAL_SECONDS

    while True:
        try:
            async for event in app.state.node_api.get_blocks_stream():
                if delay != RETRY_INITIAL_SECONDS:
                    logger.info("Reconnected to the node block stream.")
                delay = RETRY_INITIAL_SECONDS
                await store_streamed_block(app, event)
            logger.warning(f"Node block stream ended; reconnecting in {delay:.0f}s")
        except CancelledError:
            raise
        except Exception as error:
            logger.warning(f"Node block stream failed ({error!r}); reconnecting in {delay:.0f}s")

        await asyncio.sleep(delay)
        delay = min(delay * 2, RETRY_MAX_SECONDS)


async def store_streamed_block(app: "Starlette", event: BlockEvent) -> None:
    """Store one streamed block (backfilling missing ancestors), then follow the node's tip."""
    try:
        block = event.block.into_block()
        app.state.lib_slot = event.lib_slot

        db = app.state.db
        if db.block_by_hash(block.parent_block) is None:
            logger.info(f"Parent block not found for block at slot {block.slot}. Initiating chain backfill...")
            await backfill_chain_from_hash(app, block.parent_block.hex())

            if db.block_by_hash(block.parent_block) is None:
                logger.warning(
                    f"Parent block still not found after backfill for block at slot {block.slot}. Skipping block."
                )
                return

        db.store_blocks([block])
        logger.debug(f"Stored block at slot {block.slot}")

        # The node's fork choice, not ours: the event says which tip is canonical now.
        await follow_node_tip(app, event.tip)
        await backfill_missing_uncles(app, block.uncles)

    except CancelledError:
        raise
    except Exception as error:
        logger.exception(f"Error while storing new block: {error}")
