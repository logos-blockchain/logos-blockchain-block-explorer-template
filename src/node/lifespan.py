import asyncio
import logging
from asyncio import create_task
from contextlib import asynccontextmanager
from itertools import batched
from typing import TYPE_CHECKING, AsyncGenerator, AsyncIterator, List

from db.blocks import BlockRepository
from db.channels import ChannelOperationRepository
from db.clients import SqliteClient
from db.transaction import TransactionRepository
from models.block import Block
from node.api.builder import build_node_api
from node.manager.builder import build_node_manager

if TYPE_CHECKING:
    from core.app import NBE

logger = logging.getLogger(__name__)

# Safe insert size for SQLite ^3.32.0
SQLITE_BATCH_INSERT_SIZE = 10_000


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

    block_count = len(blocks_to_insert)

    # Insert all blocks in 10k batches to avoid sqlite query limits
    # allowing the first block to be a chain root if its parent doesn't exist

    for idx, batch in enumerate(batched(reversed(blocks_to_insert), SQLITE_BATCH_INSERT_SIZE)):
        first_slot = batch[0].slot
        last_slot = batch[-1].slot
        # allow_chain_root true only on first iteration
        await app.state.block_repository.create(list(batch), allow_chain_root=(idx == 0))
        logger.info(f"Backfilled {len(batch)} blocks (slots {first_slot} to {last_slot})")


@asynccontextmanager
async def node_lifespan(app: "NBE") -> AsyncGenerator[None]:
    app.state.node_manager = build_node_manager(app.settings)
    app.state.node_api = build_node_api(app.settings)

    db_client = SqliteClient(sqlite_db_path=app.settings.database_url)
    app.state.db_client = db_client
    app.state.block_repository = BlockRepository(db_client)
    app.state.transaction_repository = TransactionRepository(db_client)
    app.state.channel_repository = ChannelOperationRepository(db_client)

    try:
        logger.info("Starting node...")
        await app.state.node_manager.start()
        logger.info("Node started.")

        # Index channel ops for transactions stored before the channel index existed
        indexed = await app.state.channel_repository.backfill()
        if indexed:
            logger.info(f"Indexed {indexed} channel operations from existing transactions.")

        # Backfill to LIB on startup
        await backfill_to_lib(app)

        app.state.subscription_to_updates_handle = create_task(subscribe_to_new_blocks(app))

        yield
    finally:
        # Check if node api needs cleanup
        if hasattr(app.state.node_api, "aclose"):
            logger.info("Closing node_api connections...")
            await app.state.node_api.aclose()
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
                await app.state.block_repository.create([block])
                logger.debug(f"Stored block at slot {block_slot}")

            except Exception as error:
                logger.exception(f"Error while storing new block: {error}")
    finally:
        await _gracefully_close_stream(blocks_stream)

    logger.info("Subscription to new blocks finished.")
