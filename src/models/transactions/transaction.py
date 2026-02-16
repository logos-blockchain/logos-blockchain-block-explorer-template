import logging
from typing import List, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from core.models import TimestampedModel
from core.sqlmodel import PydanticJsonColumn
from core.types import HexBytes
from models.aliases import Fr, Gas
from models.block import Block
from models.transactions.notes import Note
from models.transactions.operations.operation import Operation

logger = logging.getLogger(__name__)


class Transaction(TimestampedModel, table=True):
    __tablename__ = "transaction"

    # --- Columns --- #

    block_id: Optional[int] = Field(default=None, foreign_key="block.id", nullable=False)
    hash: HexBytes = Field(nullable=False)
    operations: List[Operation] = Field(
        default_factory=list, sa_column=Column(PydanticJsonColumn(Operation, many=True), nullable=False)
    )
    inputs: List[Fr] = Field(default_factory=list, sa_column=Column(PydanticJsonColumn(Fr, many=True), nullable=False))
    outputs: List[Note] = Field(
        default_factory=list, sa_column=Column(PydanticJsonColumn(Note, many=True), nullable=False)
    )
    proof: HexBytes = Field(min_length=128, max_length=128, nullable=False)
    execution_gas_price: Gas
    storage_gas_price: Gas

    # --- Relationships --- #

    block: Optional[Block] = Relationship(
        back_populates="transactions",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    def __str__(self) -> str:
        return f"Transaction({self.operations})"

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, created_at={self.created_at}, operations={self.operations})>"
