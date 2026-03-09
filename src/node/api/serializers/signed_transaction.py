import hashlib
import json
from typing import List, Self

from pydantic import Field

from core.models import NbeSerializer
from models.transactions.transaction import Transaction
from node.api.serializers.fields import BytesFromIntArray
from node.api.serializers.proof import (
    OperationProofSerializer,
    OperationProofSerializerField,
)
from node.api.serializers.transaction import TransactionSerializer
from utils.protocols import FromRandom
from utils.random import random_bytes


class Groth16ProofSerializer(NbeSerializer, FromRandom):
    pi_a: BytesFromIntArray
    pi_b: BytesFromIntArray
    pi_c: BytesFromIntArray

    def to_bytes(self) -> bytes:
        return self.pi_a + self.pi_b + self.pi_c

    @classmethod
    def from_random(cls) -> Self:
        return cls.model_validate(
            {
                "pi_a": list(random_bytes(32)),
                "pi_b": list(random_bytes(64)),
                "pi_c": list(random_bytes(32)),
            }
        )


class SignedTransactionSerializer(NbeSerializer, FromRandom):
    transaction: TransactionSerializer = Field(alias="mantle_tx", description="Transaction.")
    operations_proofs: List[OperationProofSerializerField] = Field(
        alias="ops_proofs", description="List of OperationProof. Order should match `Self::transaction::operations`."
    )
    ledger_transaction_proof: Groth16ProofSerializer = Field(alias="ledger_tx_proof", description="Groth16 proof.")

    def _compute_hash(self) -> bytes:
        data = self.transaction.model_dump(mode="json")
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).digest()

    def into_transaction(self) -> Transaction:
        operations_contents = self.transaction.operations_contents
        if len(operations_contents) != len(self.operations_proofs):
            raise ValueError(
                f"Number of operations ({len(operations_contents)}) does not match number of operation proofs ({len(self.operations_proofs)})."
            )

        operations = [
            {
                "content": content.into_operation_content(),
                "proof": proof.into_operation_proof(),
            }
            for content, proof in zip(operations_contents, self.operations_proofs)
        ]

        ledger_transaction = self.transaction.ledger_transaction
        outputs = [output.into_note() for output in ledger_transaction.outputs]

        return Transaction.model_validate(
            {
                "hash": self._compute_hash(),
                "operations": operations,
                "inputs": ledger_transaction.inputs,
                "outputs": outputs,
                "proof": self.ledger_transaction_proof.to_bytes(),
                "execution_gas_price": self.transaction.execution_gas_price,
                "storage_gas_price": self.transaction.storage_gas_price,
            }
        )

    @classmethod
    def from_random(cls) -> Self:
        transaction = TransactionSerializer.from_random()
        n = len(transaction.operations_contents)
        operations_proofs = [OperationProofSerializer.from_random() for _ in range(n)]
        return cls.model_validate(
            {
                "mantle_tx": transaction,
                "ops_proofs": operations_proofs,
                "ledger_tx_proof": Groth16ProofSerializer.from_random(),
            }
        )
