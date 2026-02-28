import logging
from typing import TYPE_CHECKING, List, Optional, Self

from sqlalchemy import Column
from sqlmodel import Field, Relationship

from core.models import TimestampedModel
from core.sqlmodel import PydanticJsonColumn
from core.types import HexBytes
from models.header.proof_of_leadership import ProofOfLeadership

if TYPE_CHECKING:
    from models.transactions.transaction import Transaction


logger = logging.getLogger(__name__)


class Block(TimestampedModel, table=True):
    __tablename__ = "block"

    # --- Columns --- #

    hash: HexBytes = Field(nullable=False, unique=True)
    parent_block: HexBytes = Field(nullable=False)
    slot: int = Field(nullable=False)
    height: int = Field(nullable=False, default=0)
    fork: int = Field(nullable=False, default=0)
    block_root: HexBytes = Field(nullable=False)
    proof_of_leadership: ProofOfLeadership = Field(
        sa_column=Column(PydanticJsonColumn(ProofOfLeadership), nullable=False)
    )
    lib: Optional[HexBytes] = Field(default=None, nullable=True)
    tip: Optional[HexBytes] = Field(default=None, nullable=True)

    # --- Relationships --- #

    transactions: List["Transaction"] = Relationship(
        back_populates="block",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    def __str__(self) -> str:
        return f"Block(slot={self.slot})"

    def __repr__(self) -> str:
        return f"<Block(id={self.id}, created_at={self.created_at}, slot={self.slot}, parent={self.header["parent_block"]})>"

    def with_transactions(self, transactions: List["Transaction"]) -> Self:
        self.transactions = transactions
        return self
