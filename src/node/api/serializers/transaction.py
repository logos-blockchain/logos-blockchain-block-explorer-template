from random import randint
from typing import List, Self

from pydantic import Field

from core.models import NbeSerializer
from node.api.serializers.operation import LedgerOpSerializer, MantleOpSerializerField
from utils.protocols import FromRandom


class TransactionSerializer(NbeSerializer, FromRandom):
    ops: List[MantleOpSerializerField]
    execution_gas_price: int = Field(description="Integer in u64 format.")
    storage_gas_price: int = Field(description="Integer in u64 format.")

    @classmethod
    def from_random(cls) -> Self:
        n = 1 if randint(0, 1) <= 0.5 else randint(1, 3)
        ops = [LedgerOpSerializer.from_random() for _ in range(n)]
        return cls.model_validate(
            {
                "ops": ops,
                "execution_gas_price": randint(1, 10_000),
                "storage_gas_price": randint(1, 10_000),
            }
        )
