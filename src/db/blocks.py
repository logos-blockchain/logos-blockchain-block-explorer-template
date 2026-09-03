import logging
from typing import Dict, List, Optional

from sqlalchemy import Result, func as sa_func, update
from sqlmodel import Session, select

from db.clients import DbClient
from models.block import Block
from models.channel_operation import channel_operations_for_blocks

logger = logging.getLogger(__name__)


class BlockRepository:
    def __init__(self, client: DbClient):
        self.client = client

    async def create(self, blocks: List[Block], allow_chain_root: bool = False) -> None:
        """
        Insert blocks, assign heights from their parents, and extend the canonical chain.

        Args:
            blocks: Blocks to insert. Blocks already stored (by hash) are skipped.
            allow_chain_root: If True, allow the first block (by slot) to be a chain root
                             even if its parent doesn't exist. Used during chain-walk backfills.
        """
        if not blocks:
            return

        with self.client.session() as session:
            # The live stream can deliver a block that a chain-walk backfill has
            # just inserted; skip anything we already have.
            already_stored = set(session.exec(select(Block.hash).where(Block.hash.in_([b.hash for b in blocks]))).all())
            blocks = [block for block in blocks if block.hash not in already_stored]
            if not blocks:
                return

            # Collect all unique parent hashes we need to look up
            parent_hashes = {block.parent_block for block in blocks}

            # Fetch existing parent blocks to get their heights
            parent_heights: Dict[bytes, int] = {}
            if parent_hashes:
                statement = select(Block.hash, Block.height).where(Block.hash.in_(parent_hashes))
                for parent_hash, parent_height in session.exec(statement).all():
                    parent_heights[parent_hash] = parent_height

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
            if not blocks_to_add:
                return

            session.add_all(blocks_to_add)
            # Flush so blocks/transactions get ids, then index channel ops in
            # the same commit so the index can never drift from the chain.
            session.flush()
            session.add_all(channel_operations_for_blocks(blocks_to_add))

            # Longest chain wins; on a tie the current chain stays canonical.
            candidate = max(blocks_to_add, key=lambda b: b.height)
            current_tip_height = session.exec(select(sa_func.max(Block.height)).where(Block.canonical)).one()
            if current_tip_height is None or candidate.height > current_tip_height:
                _switch_canonical_chain(session, candidate)

            session.commit()

    async def get_by_hash(self, block_hash: bytes) -> Optional[Block]:
        statement = select(Block).where(Block.hash == block_hash)

        with self.client.session() as session:
            result: Result[Block] = session.exec(statement)
            return result.one_or_none()

    async def get_latest(self, limit: int) -> List[Block]:
        """The newest `limit` canonical blocks, oldest-first."""
        if limit == 0:
            return []

        statement = select(Block).where(Block.canonical).order_by(Block.height.desc()).limit(limit)
        with self.client.session() as session:
            return list(reversed(session.exec(statement).all()))

    async def get_since(self, block_id: int, *, limit: int = 500) -> List[Block]:
        """Canonical blocks inserted after `block_id`, oldest-first. Drives the live stream."""
        statement = select(Block).where(Block.canonical, Block.id > block_id).order_by(Block.id.asc()).limit(limit)
        with self.client.session() as session:
            return session.exec(statement).all()

    async def get_paginated(self, page: int, page_size: int) -> tuple[List[Block], int]:
        """Canonical blocks, newest first, plus the canonical chain length."""
        offset = page * page_size

        with self.client.session() as session:
            total_count = session.exec(select(sa_func.count()).select_from(Block).where(Block.canonical)).one()
            statement = (
                select(Block).where(Block.canonical).order_by(Block.height.desc()).offset(offset).limit(page_size)
            )
            blocks = session.exec(statement).all()

        return blocks, total_count


def _switch_canonical_chain(session: Session, tip: Block) -> int:
    """Make the chain ending at `tip` canonical.

    Walks parent links from `tip` until it reaches a block that is already
    canonical (the common ancestor) or the root. Blocks on the old chain above
    the ancestor are un-flagged, the walked path is flagged. Returns the number
    of blocks flagged.
    """
    path_ids: List[int] = []
    ancestor_height = 0
    current: Optional[Block] = tip
    while current is not None and not current.canonical:
        path_ids.append(current.id)
        current = session.exec(select(Block).where(Block.hash == current.parent_block)).first()
    if current is not None:
        ancestor_height = current.height

    if path_ids:
        session.exec(update(Block).where(Block.canonical, Block.height > ancestor_height).values(canonical=False))
        for start in range(0, len(path_ids), 500):
            session.exec(update(Block).where(Block.id.in_(path_ids[start : start + 500])).values(canonical=True))
        # Keep the in-memory objects consistent with what was just written.
        for block in session.identity_map.values():
            if isinstance(block, Block) and block.id in path_ids:
                block.canonical = True
    if len(path_ids) > 1:
        logger.info(f"Canonical chain switched: {len(path_ids)} blocks above height {ancestor_height} now canonical")
    return len(path_ids)
