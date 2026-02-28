from typing import List, Optional, Self

from core.models import NbeSchema
from core.types import HexBytes
from models.block import Block
from models.header.proof_of_leadership import ProofOfLeadership
from models.transactions.transaction import Transaction


class BlockRead(NbeSchema):
    id: int
    hash: HexBytes
    parent_block_hash: HexBytes
    slot: int
    height: int
    fork: int
    block_root: HexBytes
    proof_of_leadership: ProofOfLeadership
    lib: Optional[HexBytes] = None
    tip: Optional[HexBytes] = None
    transactions: List[Transaction]

    @classmethod
    def from_block(cls, block: Block) -> Self:
        return cls(
            id=block.id,
            hash=block.hash,
            parent_block_hash=block.parent_block,
            slot=block.slot,
            height=block.height,
            fork=block.fork,
            block_root=block.block_root,
            proof_of_leadership=block.proof_of_leadership,
            lib=block.lib,
            tip=block.tip,
            transactions=block.transactions,
        )
