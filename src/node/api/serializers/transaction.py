from random import randint
from typing import List, Self

from pydantic import Field

from core.models import NbeSerializer
from node.api.serializers.ledger_transaction import LedgerTransactionSerializer
from node.api.serializers.operation import (
    OperationContentSerializer,
    OperationContentSerializerField,
)
from utils.protocols import FromRandom
from utils.random import random_bytes


class TransactionSerializer(NbeSerializer, FromRandom):
    operations_contents: List[OperationContentSerializerField] = Field(alias="ops")
    ledger_transaction: LedgerTransactionSerializer = Field(alias="ledger_tx")
    execution_gas_price: int = Field(description="Integer in u64 format.")
    storage_gas_price: int = Field(description="Integer in u64 format.")

    @classmethod
    def from_random(cls) -> Self:
        n = 0 if randint(0, 1) <= 0.5 else randint(1, 5)
        operations_contents = [OperationContentSerializer.from_random() for _ in range(n)]
        return cls.model_validate(
            {
                "ops": operations_contents,
                "ledger_tx": LedgerTransactionSerializer.from_random(),
                "execution_gas_price": randint(1, 10_000),
                "storage_gas_price": randint(1, 10_000),
            }
        )
