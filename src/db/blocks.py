import logging
from asyncio import sleep
from typing import AsyncIterator, Dict, List, Optional
from sqlalchemy import Result, Select, func as sa_func
from sqlalchemy.orm import aliased
from sqlmodel import select

from db.clients import DbClient
from models.block import Block
from models.channel_operation import channel_operations_for_blocks

logger = logging.getLogger(__name__)


def chain_block_ids_cte(*, fork: int):
    """
    Recursive CTE that collects all block IDs on the chain from the tip
    of the given fork back to genesis, following parent_block links.

    This correctly traverses across fork boundaries — e.g. if fork 1 diverged
    from fork 0 at height 50, the CTE returns fork 1 blocks (50+) AND the
    ancestor fork 0 blocks (0–49).
    """
    tip_hash = select(Block.hash).where(Block.fork == fork).order_by(Block.height.desc()).limit(1).scalar_subquery()

    base = select(Block.id, Block.hash, Block.parent_block).where(Block.hash == tip_hash)
    cte = base.cte(name="chain", recursive=True)

    recursive = select(Block.id, Block.hash, Block.parent_block).where(Block.hash == cte.c.parent_block)
    return cte.union_all(recursive)


def get_latest_statement(limit: int, *, fork: int, output_ascending: bool = True) -> Select:
    chain = chain_block_ids_cte(fork=fork)
    base = select(Block).join(chain, Block.id == chain.c.id).order_by(Block.height.desc()).limit(limit)
    if not output_ascending:
        return base

    # Reorder for output
    inner = base.subquery()
    latest = aliased(Block, inner)
    return select(latest).options().order_by(latest.height.asc())  # type: ignore[arg-type]


class BlockRepository:
    def __init__(self, client: DbClient):
        self.client = client

    async def create(self, blocks: List[Block], allow_chain_root: bool = False) -> None:
        """
        Insert blocks into the database with proper height calculation.

        Args:
            blocks: Blocks to insert
            allow_chain_root: If True, allow the first block (by slot) to be a chain root
                             even if its parent doesn't exist. Used during chain-walk backfills.
        """
        if not blocks:
            return

        with self.client.session() as session:
            # Collect all unique parent hashes we need to look up
            parent_hashes = {block.parent_block for block in blocks}

            # Fetch existing parent blocks to get their heights
            parent_heights: Dict[bytes, int] = {}
            if parent_hashes:
                statement = select(Block).where(Block.hash.in_(parent_hashes))
                existing_parents = session.exec(statement).all()
                for parent in existing_parents:
                    parent_heights[parent.hash] = parent.height

            # Also check if any of the blocks we're inserting are parents of others
            blocks_by_hash = {block.hash: block for block in blocks}

            # Find the chain root candidate (lowest slot block whose parent isn't in the batch)
            chain_root_hash = None
            if allow_chain_root:
                sorted_blocks = sorted(blocks, key=lambda b: b.slot)
                for block in sorted_blocks:
                    if block.parent_block not in blocks_by_hash and block.parent_block not in parent_heights:
                        chain_root_hash = block.hash
                        break

            # Handle blocks in batch that depend on each other
            # Resolve dependencies iteratively, skipping orphans
            resolved = set()
            orphans = set()
            max_iterations = len(blocks) * 2  # Prevent infinite loops
            iterations = 0

            while iterations < max_iterations:
                iterations += 1
                made_progress = False

                for block in blocks:
                    if block.hash in resolved or block.hash in orphans:
                        continue

                    if block.parent_block in parent_heights:
                        # Parent found in DB or already resolved
                        block.height = parent_heights[block.parent_block] + 1
                        parent_heights[block.hash] = block.height
                        resolved.add(block.hash)
                        made_progress = True
                    elif block.parent_block in blocks_by_hash:
                        parent = blocks_by_hash[block.parent_block]
                        if parent.hash in resolved:
                            # Parent in same batch and already resolved
                            block.height = parent.height + 1
                            parent_heights[block.hash] = block.height
                            resolved.add(block.hash)
                            made_progress = True
                        elif parent.hash in orphans:
                            # Parent is an orphan, so this block is also an orphan
                            orphans.add(block.hash)
                            made_progress = True
                        # else: parent not yet resolved, try again next iteration
                    else:
                        # Parent not found anywhere
                        if block.slot == 0 or block.hash == chain_root_hash:
                            # Genesis block or chain root - no parent requirement.
                            # Height starts at 1 to count the genesis block itself,
                            # so chain height = total number of blocks.
                            # See: https://github.com/logos-blockchain/logos-blockchain-block-explorer-template/issues/12
                            block.height = 1
                            parent_heights[block.hash] = block.height
                            resolved.add(block.hash)
                            made_progress = True
                            if block.hash == chain_root_hash:
                                logger.info(
                                    f"Chain root block: hash={block.hash.hex()[:16]}..., "
                                    f"slot={block.slot}, height=1"
                                )
                        else:
                            # Orphan block - parent doesn't exist
                            logger.warning(
                                f"Dropping orphaned block: hash={block.hash.hex()}, "
                                f"slot={block.slot}, parent={block.parent_block.hex()} (parent not found)"
                            )
                            orphans.add(block.hash)
                            made_progress = True

                # If no progress was made and we still have unresolved blocks, break
                if not made_progress:
                    break

            # Check for any blocks that couldn't be resolved (circular dependencies or other issues)
            unresolved = set(block.hash for block in blocks) - resolved - orphans
            for block in blocks:
                if block.hash in unresolved:
                    logger.warning(
                        f"Dropping unresolvable block: hash={block.hash.hex()}, "
                        f"slot={block.slot}, parent={block.parent_block.hex()}"
                    )

            # Only add resolved blocks
            blocks_to_add = [block for block in blocks if block.hash in resolved]

            # --- Fork assignment ---
            if blocks_to_add:
                # Build lookup of parent_block -> fork for parents already in DB
                parent_forks: Dict[bytes, int] = {}
                if parent_hashes:
                    stmt = select(Block.hash, Block.fork).where(Block.hash.in_(parent_hashes))
                    for phash, pfork in session.exec(stmt).all():
                        parent_forks[phash] = pfork

                # Also include fork info from blocks in this batch that are parents
                for block in blocks_to_add:
                    if block.hash in parent_hashes:
                        parent_forks[block.hash] = block.fork

                # Find which parents already have children in the DB
                parent_hashes_in_batch = {b.parent_block for b in blocks_to_add}
                parents_with_children: set[bytes] = set()
                if parent_hashes_in_batch:
                    stmt = select(Block.parent_block).where(Block.parent_block.in_(parent_hashes_in_batch)).distinct()
                    for ph in session.exec(stmt).all():
                        parents_with_children.add(ph)

                # Get current max fork across the whole DB
                max_fork_result = session.exec(select(sa_func.max(Block.fork))).one_or_none()
                next_fork = (max_fork_result or 0) + 1

                # Also account for forks assigned within this batch
                batch_children_count: Dict[bytes, int] = {}

                for block in blocks_to_add:
                    parent = block.parent_block
                    already_has_child_in_db = parent in parents_with_children
                    children_assigned_in_batch = batch_children_count.get(parent, 0)

                    if already_has_child_in_db or children_assigned_in_batch > 0:
                        # Another block with the same parent exists -> new fork
                        block.fork = next_fork
                        next_fork += 1
                    elif parent in parent_forks:
                        # No sibling -> inherit parent's fork
                        block.fork = parent_forks[parent]
                    else:
                        # Genesis / chain root with no parent -> fork 0
                        block.fork = 0

                    batch_children_count[parent] = children_assigned_in_batch + 1
                    # Make this block's fork available for its children in the batch
                    parent_forks[block.hash] = block.fork

            if blocks_to_add:
                session.add_all(blocks_to_add)
                # Flush so blocks/transactions get ids, then index channel ops in
                # the same commit so the index can never drift from the chain.
                session.flush()
                session.add_all(channel_operations_for_blocks(blocks_to_add))
                session.commit()

    async def get_by_id(self, block_id: int) -> Optional[Block]:
        statement = select(Block).where(Block.id == block_id)

        with self.client.session() as session:
            result: Result[Block] = session.exec(statement)
            return result.one_or_none()

    async def get_by_hash(self, block_hash: bytes) -> Optional[Block]:
        statement = select(Block).where(Block.hash == block_hash)

        with self.client.session() as session:
            result: Result[Block] = session.exec(statement)
            return result.one_or_none()

    async def get_latest(self, limit: int, *, fork: int, ascending: bool = True) -> List[Block]:
        if limit == 0:
            return []

        statement = get_latest_statement(limit, fork=fork, output_ascending=ascending)

        with self.client.session() as session:
            results: Result[Block] = session.exec(statement)
            b = results.all()
            return b

    async def get_fork_choice(self) -> Optional[int]:
        """Return the fork number of the longest chain (block with max height)."""
        statement = select(Block.fork).order_by(Block.height.desc()).limit(1)
        with self.client.session() as session:
            return session.exec(statement).one_or_none()

    async def get_earliest(self) -> Optional[Block]:
        statement = select(Block).order_by(Block.height.asc()).limit(1)

        with self.client.session() as session:
            results: Result[Block] = session.exec(statement)
            return results.one_or_none()

    async def get_paginated(self, page: int, page_size: int, *, fork: int) -> tuple[List[Block], int]:
        """
        Get blocks with pagination, ordered by height descending (newest first).
        Follows the chain from the fork's tip back to genesis across fork boundaries.
        Returns a tuple of (blocks, total_count).
        """
        offset = page * page_size
        chain = chain_block_ids_cte(fork=fork)

        with self.client.session() as session:
            count_statement = select(sa_func.count()).select_from(chain)
            total_count = session.exec(count_statement).one()

            statement = (
                select(Block)
                .join(chain, Block.id == chain.c.id)
                .order_by(Block.height.desc())
                .offset(offset)
                .limit(page_size)
            )
            blocks = session.exec(statement).all()

        return blocks, total_count

    async def updates_stream(
        self, block_from: Optional[Block], *, fork: int, timeout_seconds: int = 1
    ) -> AsyncIterator[List[Block]]:
        height_cursor: int = block_from.height + 1 if block_from is not None else 0

        while True:
            statement = (
                select(Block).where(Block.fork == fork, Block.height >= height_cursor).order_by(Block.height.asc())
            )

            with self.client.session() as session:
                blocks: List[Block] = session.exec(statement).all()

            if len(blocks) > 0:
                height_cursor = blocks[-1].height + 1
                yield blocks
            else:
                await sleep(timeout_seconds)
