from typing import List, Self

from core.models import NbeSchema
from core.types import HexBytes
from models.aliases import Gas
from models.transactions.operations.operation import Operation
from models.transactions.transaction import Transaction


class TransactionRead(NbeSchema):
    id: int
    block_hash: HexBytes
    hash: HexBytes
    operations: List[Operation]
    execution_gas_price: Gas
    storage_gas_price: Gas

    @classmethod
    def from_transaction(cls, transaction: Transaction) -> Self:
        return cls(
            id=transaction.id,
            block_hash=transaction.block.hash,
            hash=transaction.hash,
            operations=transaction.operations,
            execution_gas_price=transaction.execution_gas_price,
            storage_gas_price=transaction.storage_gas_price,
        )
