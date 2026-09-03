from typing import List, Self

from core.models import NbeSchema
from core.types import HexBytes
from models.block import Block
from models.header.proof_of_leadership import ProofOfLeadership
from models.transactions.transaction import Transaction


class BlockSummary(NbeSchema):
    """Block row for lists and the live stream: no proof, transaction count only."""

    id: int
    hash: HexBytes
    parent_block_hash: HexBytes
    slot: int
    height: int
    block_root: HexBytes
    transaction_count: int

    @classmethod
    def from_block(cls, block: Block) -> Self:
        return cls(
            id=block.id,
            hash=block.hash,
            parent_block_hash=block.parent_block,
            slot=block.slot,
            height=block.height,
            block_root=block.block_root,
            transaction_count=len(block.transactions),
        )


class BlockRead(NbeSchema):
    id: int
    hash: HexBytes
    parent_block_hash: HexBytes
    slot: int
    height: int
    canonical: bool
    block_root: HexBytes
    proof_of_leadership: ProofOfLeadership
    transactions: List[Transaction]

    @classmethod
    def from_block(cls, block: Block) -> Self:
        return cls(
            id=block.id,
            hash=block.hash,
            parent_block_hash=block.parent_block,
            slot=block.slot,
            height=block.height,
            canonical=block.canonical,
            block_root=block.block_root,
            proof_of_leadership=block.proof_of_leadership,
            transactions=block.transactions,
        )
