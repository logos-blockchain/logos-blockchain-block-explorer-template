from typing import List, Self

from core.models import NbeSchema
from core.types import HexBytes
from models.transactions.operations.operation import Operation
from models.transactions.transaction import Transaction


class TransactionRead(NbeSchema):
    id: int
    block_hash: HexBytes
    hash: HexBytes
    # False when the only copy of this transaction sits in an orphaned block.
    canonical: bool
    operations: List[Operation]

    @classmethod
    def from_transaction(cls, transaction: Transaction) -> Self:
        return cls(
            id=transaction.id,
            block_hash=transaction.block.hash,
            hash=transaction.hash,
            canonical=transaction.block.canonical,
            operations=transaction.operations,
        )
