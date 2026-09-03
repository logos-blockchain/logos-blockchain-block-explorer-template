import logging
from typing import List, Optional

from sqlalchemy import Column
from sqlmodel import Field, Relationship

from core.models import IdNbeModel
from core.sqlmodel import PydanticJsonColumn
from core.types import HexBytes
from models.block import Block
from models.transactions.operations.operation import Operation

logger = logging.getLogger(__name__)


class Transaction(IdNbeModel, table=True):
    __tablename__ = "transaction"

    # --- Columns --- #

    block_id: Optional[int] = Field(default=None, foreign_key="block.id", nullable=False, index=True)
    # Not unique: the same transaction can be included by competing blocks.
    hash: HexBytes = Field(nullable=False, index=True)
    operations: List[Operation] = Field(
        default_factory=list, sa_column=Column(PydanticJsonColumn(Operation, many=True), nullable=False)
    )

    # --- Relationships --- #

    block: Optional[Block] = Relationship(
        back_populates="transactions",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    def __str__(self) -> str:
        return f"Transaction({self.operations})"

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, hash={self.hash.hex()[:16]}..., operations={len(self.operations)})>"
