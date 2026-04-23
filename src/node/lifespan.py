import asyncio
import logging
from asyncio import create_task
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncGenerator, AsyncIterator, List

from db.blocks import BlockRepository
from db.clients import SqliteClient
from db.transaction import TransactionRepository
from models.block import Block
from node.api.builder import build_node_api
from node.manager.builder import build_node_manager

if TYPE_CHECKING:
    from core.app import NBE

logger = logging.getLogger(__name__)


async def backfill_to_lib(app: "NBE") -> None:
    """
    Fetch the LIB (Last Irreversible Block) from the node and backfill by walking the chain backwards.
    This traverses parent links instead of querying by slot range, which handles pruned/missing blocks.
    Retries indefinitely with exponential backoff on failure.
    """
    delay = 1.0
    max_delay = 60.0

    while True:
        try:
            info = await app.state.node_api.get_info()
            logger.info(f"Node info: LIB={info.lib}, tip={info.tip}, slot={info.slot}, height={info.height}")

            logger.debug(f"Block {info.lib}...")
            await backfill_chain_from_hash(app, info.lib)
            return

        except Exception as error:
            logger.exception(f"Error during initial backfill to LIB: {error}")
            logger.info(f"Retrying backfill in {delay:.0f}s...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)


async def backfill_chain_from_hash(app: "NBE", block_hash: str) -> None:
    """
    Walk the chain backwards from block_hash, fetching blocks until we hit
    a block we already have or a genesis block (parent doesn't exist).
    """
    blocks_to_insert: List[Block] = []
    current_hash = block_hash

    while True:
        # Check if we already have this block
        logger.debug(f"Block {current_hash}...")
        existing = await app.state.block_repository.get_by_hash(bytes.fromhex(current_hash))
        if existing.is_some:
            logger.debug(f"Block {current_hash[:16]}... already exists, stopping chain walk")
            break

        # Fetch the block from the node
        block_serializer = await app.state.node_api.get_block_by_hash(current_hash)
        if block_serializer is None:
            logger.info(f"Block {current_hash[:16]}... not found on node (likely genesis parent), stopping chain walk")
            break

        block = block_serializer.into_block()
        blocks_to_insert.append(block)
        logger.debug(f"Queued block at slot {block.slot} (hash={current_hash[:16]}...) for insertion")

        # Move to parent
        current_hash = block.parent_block.hex()

    if not blocks_to_insert:
        logger.info("No new blocks to backfill")
        return

    # Reverse so we insert from oldest to newest (parent before child)
    blocks_to_insert.reverse()

    # Capture slot range before insert (blocks get detached from session after commit)
    first_slot = blocks_to_insert[0].slot
    last_slot = blocks_to_insert[-1].slot
    block_count = len(blocks_to_insert)

    logger.info(f"Backfilling {block_count} blocks from chain walk...")

    # Insert all blocks, allowing the first one to be a chain root if its parent doesn't exist
    await app.state.block_repository.create(*blocks_to_insert, allow_chain_root=True)
    logger.info(f"Backfilled {block_count} blocks (slots {first_slot} to {last_slot})")


@asynccontextmanager
async def node_lifespan(app: "NBE") -> AsyncGenerator[None]:
    app.state.node_manager = build_node_manager(app.settings)
    app.state.node_api = build_node_api(app.settings)

    db_client = SqliteClient()
    app.state.db_client = db_client
    app.state.block_repository = BlockRepository(db_client)
    app.state.transaction_repository = TransactionRepository(db_client)

    try:
        logger.info("Starting node...")
        await app.state.node_manager.start()
        logger.info("Node started.")

        # Backfill to LIB on startup
        await backfill_to_lib(app)

        app.state.subscription_to_updates_handle = create_task(subscribe_to_new_blocks(app))

        yield
    finally:
        logger.info("Stopping node...")
        await app.state.node_manager.stop()
        logger.info("Node stopped.")


async def _gracefully_close_stream(stream: AsyncIterator) -> None:
    aclose = getattr(stream, "aclose", None)
    if aclose is not None:
        try:
            await aclose()
        except Exception as e:
            logger.error(f"Error while closing the new blocks stream: {e}")


async def subscribe_to_new_blocks(app: "NBE"):
    logger.info("Subscription to new blocks started.")
    blocks_stream = app.state.node_api.get_blocks_stream()

    try:
        while app.state.is_running:
            try:
                block_serializer = await anext(blocks_stream)
            except TimeoutError:
                continue
            except StopAsyncIteration:
                logger.error("Subscription to the new blocks stream ended unexpectedly. Please restart the node.")
                break
            except Exception as error:
                logger.exception(f"Error while fetching new blocks: {error}")
                continue

            try:
                block = block_serializer.into_block()

                # Check if parent exists in DB
                parent_exists = (await app.state.block_repository.get_by_hash(block.parent_block)).is_some

                if not parent_exists:
                    # Need to backfill the chain from this block's parent
                    logger.info(f"Parent block not found for block at slot {block.slot}. Initiating chain backfill...")
                    await backfill_chain_from_hash(app, block.parent_block.hex())

                    # Re-check if parent now exists after backfill
                    parent_exists = (await app.state.block_repository.get_by_hash(block.parent_block)).is_some
                    if not parent_exists:
                        logger.warning(
                            f"Parent block still not found after backfill for block at slot {block.slot}. Skipping block."
                        )
                        continue

                # Capture values before create() detaches the block from the session
                block_slot = block.slot

                # Now we have the parent, store the block
                await app.state.block_repository.create(block)
                logger.debug(f"Stored block at slot {block_slot}")

            except Exception as error:
                logger.exception(f"Error while storing new block: {error}")
    finally:
        await _gracefully_close_stream(blocks_stream)

    logger.info("Subscription to new blocks finished.")
