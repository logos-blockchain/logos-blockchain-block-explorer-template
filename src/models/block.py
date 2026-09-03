from typing import List, Optional

from pydantic import Field

from core.models import NbeSchema
from core.types import HexBytes
from models.header.proof_of_leadership import ProofOfLeadership
from models.header.uncle import UncleHeader
from models.transactions.transaction import Transaction


class Block(NbeSchema):
    """A stored block. `id`, `height`, `canonical` and `canonical_seq` are assigned by the database."""

    id: Optional[int] = None
    hash: HexBytes
    parent_block: HexBytes
    slot: int
    height: int = 0
    canonical: bool = False
    canonical_seq: int = 0
    block_root: HexBytes
    proof_of_leadership: ProofOfLeadership
    # Competing blocks this block references (Bedrock uncle references).
    uncles: List[UncleHeader] = Field(default_factory=list)
    transactions: List[Transaction] = Field(default_factory=list)

    def __str__(self) -> str:
        return f"Block(slot={self.slot})"

    def __repr__(self) -> str:
        return (
            f"<Block(id={self.id}, slot={self.slot}, height={self.height}, canonical={self.canonical}, "
            f"parent={self.parent_block.hex()[:16]}...)>"
        )
