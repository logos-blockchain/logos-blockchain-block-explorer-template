import logging
from typing import TYPE_CHECKING, List, Self

from sqlalchemy import Column, Index
from sqlmodel import Field, Relationship

from core.models import IdNbeModel
from core.sqlmodel import PydanticJsonColumn
from core.types import HexBytes
from models.header.proof_of_leadership import ProofOfLeadership
from models.header.uncle import UncleHeader

if TYPE_CHECKING:
    from models.transactions.transaction import Transaction


logger = logging.getLogger(__name__)


class Block(IdNbeModel, table=True):
    __tablename__ = "block"
    # (canonical, height) serves every "walk the chain newest-first" query;
    # parent_block serves ingestion's sibling/parent lookups.
    __table_args__ = (Index("ix_block_canonical_height", "canonical", "height"),)

    # --- Columns --- #

    hash: HexBytes = Field(nullable=False, unique=True)
    parent_block: HexBytes = Field(nullable=False, index=True)
    slot: int = Field(nullable=False)
    height: int = Field(nullable=False, default=0, index=True)
    # True for blocks on the longest chain the explorer knows about. Maintained
    # by BlockRepository at insert time; a reorg flips the flag on the blocks
    # above the common ancestor.
    canonical: bool = Field(nullable=False, default=False)
    # Monotonic stamp taken whenever a block becomes canonical. Live streams
    # cursor on it, so a block that turns canonical in a reorg is still
    # delivered even though its row id is older than blocks already sent.
    canonical_seq: int = Field(nullable=False, default=0, index=True)
    block_root: HexBytes = Field(nullable=False)
    proof_of_leadership: ProofOfLeadership = Field(
        sa_column=Column(PydanticJsonColumn(ProofOfLeadership), nullable=False)
    )
    # Competing blocks this block references (Bedrock uncle references).
    uncles: List[UncleHeader] = Field(
        default_factory=list, sa_column=Column(PydanticJsonColumn(UncleHeader, many=True), nullable=False)
    )

    # --- Relationships --- #

    transactions: List["Transaction"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    def __str__(self) -> str:
        return f"Block(slot={self.slot})"

    def __repr__(self) -> str:
        return (
            f"<Block(id={self.id}, slot={self.slot}, height={self.height}, canonical={self.canonical}, "
            f"parent={self.parent_block.hex()[:16]}...)>"
        )

    def with_transactions(self, transactions: List["Transaction"]) -> Self:
        self.transactions = transactions
        return self
