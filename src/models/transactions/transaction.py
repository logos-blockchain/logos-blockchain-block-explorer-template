from typing import List, Optional

from pydantic import Field

from core.models import NbeSchema
from core.types import HexBytes
from models.transactions.operations.operation import Operation


class Transaction(NbeSchema):
    """A stored transaction. `id` and `block_id` are assigned by the database."""

    id: Optional[int] = None
    block_id: Optional[int] = None
    hash: HexBytes
    operations: List[Operation] = Field(default_factory=list)

    def __str__(self) -> str:
        return f"Transaction({self.operations})"

    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, hash={self.hash.hex()[:16]}..., operations={len(self.operations)})>"
