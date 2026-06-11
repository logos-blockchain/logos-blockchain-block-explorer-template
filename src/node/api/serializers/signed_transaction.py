import hashlib
import json
from typing import List, Self

from pydantic import Field

from core.models import NbeSerializer
from models.transactions.transaction import Transaction
from node.api.serializers.operation import (
    ChannelInscribeOpSerializer,
    LedgerOpSerializer,
)
from node.api.serializers.proof import (
    Ed25519SignatureSerializer,
    OperationProofSerializerField,
    ZkSignatureSerializer,
)
from node.api.serializers.transaction import TransactionSerializer
from utils.protocols import FromRandom


class SignedTransactionSerializer(NbeSerializer, FromRandom):
    transaction: TransactionSerializer = Field(alias="mantle_tx", description="Transaction.")
    operations_proofs: List[OperationProofSerializerField] = Field(
        alias="ops_proofs",
        description="List of OperationProof. Order should match `Self::transaction::ops`.",
    )

    def _compute_hash(self) -> bytes:
        data = self.transaction.model_dump(mode="json")
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).digest()

    def into_transaction(self) -> Transaction:
        ops = self.transaction.ops
        if len(ops) != len(self.operations_proofs):
            raise ValueError(
                f"Number of ops ({len(ops)}) does not match number of op proofs "
                f"({len(self.operations_proofs)})."
            )

        operations: List[dict] = []
        for op, proof in zip(ops, self.operations_proofs):
            if isinstance(op, LedgerOpSerializer):
                if not isinstance(proof, ZkSignatureSerializer):
                    raise ValueError(
                        f"Expected a ZkSig (Groth16) proof for the ledger op, got {type(proof).__name__}."
                    )
                operations.append(
                    {
                        "content": {
                            "type": "LedgerTransfer",
                            "inputs": list(op.inputs),
                            "outputs": [o.into_note() for o in op.outputs],
                        },
                        "proof": {
                            "type": "Zk",
                            "signature": proof.to_bytes(),
                        },
                    }
                )
            elif isinstance(op, ChannelInscribeOpSerializer):
                if not isinstance(proof, Ed25519SignatureSerializer):
                    raise ValueError(
                        f"Expected an Ed25519Sig proof for the channel inscribe op, got {type(proof).__name__}."
                    )
                operations.append(
                    {
                        "content": {
                            "type": "ChannelInscribe",
                            "channel_id": op.channel_id,
                            "inscription": op.inscription,
                            "parent": op.parent,
                            "signer": op.signer,
                        },
                        "proof": {
                            "type": "Ed25519",
                            "signature": proof.root,
                        },
                    }
                )
            else:
                # Gracefully handle unknown ops. We assume that whatever comes from the node is correct.
                operations.append({
                    "content": {
                        "type": "UnknownOp",
                        "opcode": getattr(op, "opcode", "unknown"),
                        "raw_payload": op.model_dump() if hasattr(op, "model_dump") else str(op),
                    },
                    "proof": {
                        "type": "Unknown",
                        "signature": proof.to_bytes() if hasattr(proof, "to_bytes") else getattr(proof, "root", b""),
                    },
                })

        return Transaction.model_validate(
            {
                "hash": self._compute_hash(),
                "operations": operations,
                "execution_gas_price": self.transaction.execution_gas_price,
                "storage_gas_price": self.transaction.storage_gas_price,
            }
        )

    @classmethod
    def from_random(cls) -> Self:
        transaction = TransactionSerializer.from_random()
        operations_proofs = [ZkSignatureSerializer.from_random() for _ in range(len(transaction.ops))]
        return cls.model_validate(
            {
                "mantle_tx": transaction,
                "ops_proofs": operations_proofs,
            }
        )
