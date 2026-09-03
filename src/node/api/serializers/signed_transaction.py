import hashlib
import json
from typing import List, Self

from pydantic import Field

from core.models import NbeSerializer
from models.transactions.transaction import Transaction
from node.api.serializers.operation import (
    ChannelConfigOpSerializer,
    ChannelDepositOpSerializer,
    ChannelInscribeOpSerializer,
    ChannelTransferOpSerializer,
    ChannelWithdrawOpSerializer,
    ClaimPowRewardOpSerializer,
    LeaderClaimOpSerializer,
    LedgerOpSerializer,
    SDPActiveOpSerializer,
    SDPDeclareOpSerializer,
    SDPWithdrawOpSerializer,
    UnknownOpSerializer,
)
from node.api.serializers.proof import (
    ChannelMultiSigProofSerializer,
    Ed25519SignatureSerializer,
    NoneProofSerializer,
    OperationProofSerializerField,
    PoCProofSerializer,
    UnknownProofSerializer,
    ZkAndEd25519SignaturesSerializer,
    ZkSignatureSerializer,
)
from node.api.serializers.transaction import TransactionSerializer
from utils.protocols import FromRandom


def _proof_to_internal(proof) -> dict:
    if isinstance(proof, ZkSignatureSerializer):
        return {"type": "Zk", "signature": proof.to_bytes()}
    if isinstance(proof, Ed25519SignatureSerializer):
        return {"type": "Ed25519", "signature": proof.root}
    if isinstance(proof, ZkAndEd25519SignaturesSerializer):
        return {
            "type": "ZkAndEd25519",
            "zk_signature": proof.zk_signature.to_bytes(),
            "ed25519_signature": proof.ed25519_signature,
        }
    if isinstance(proof, PoCProofSerializer):
        return {"type": "PoC", "proof": proof.proof}
    if isinstance(proof, ChannelMultiSigProofSerializer):
        return {
            "type": "ChannelMultiSig",
            "signatures": [
                {"signature": s.signature, "channel_key_index": s.channel_key_index} for s in proof.signatures
            ],
        }
    if isinstance(proof, NoneProofSerializer):
        return {"type": "None"}
    if isinstance(proof, UnknownProofSerializer):
        return {"type": "Unknown", "raw": proof.raw}
    raise ValueError(f"Unsupported proof type: {type(proof).__name__}")


def _op_to_content(op) -> dict:
    if isinstance(op, LedgerOpSerializer):
        return {
            "type": "LedgerTransfer",
            "inputs": list(op.inputs),
            "outputs": [o.into_note() for o in op.outputs],
        }
    if isinstance(op, ChannelConfigOpSerializer):
        return {
            "type": "ChannelConfig",
            "channel": op.channel,
            "parent": op.parent,
            "keys": list(op.keys),
            "posting_timeframe": op.posting_timeframe,
            "posting_timeout": op.posting_timeout,
            "configuration_threshold": op.configuration_threshold,
            "transfer_threshold": op.transfer_threshold,
        }
    if isinstance(op, ChannelInscribeOpSerializer):
        return {
            "type": "ChannelInscribe",
            "channel_id": op.channel_id,
            "inscription": op.inscription,
            "parent": op.parent,
            "signer": op.signer,
        }
    if isinstance(op, ChannelDepositOpSerializer):
        return {
            "type": "ChannelDeposit",
            "channel_id": op.channel_id,
            "inputs": list(op.inputs),
            "metadata": op.metadata,
        }
    if isinstance(op, ChannelWithdrawOpSerializer):
        return {
            "type": "ChannelWithdraw",
            "channel_id": op.channel_id,
            "inputs": list(op.inputs),
        }
    if isinstance(op, ChannelTransferOpSerializer):
        return {
            "type": "ChannelTransfer",
            "channel_id": op.channel_id,
            "inputs": list(op.inputs),
            "outputs": [o.into_note() for o in op.outputs],
        }
    if isinstance(op, SDPDeclareOpSerializer):
        return {
            "type": "SDPDeclare",
            "service_type": op.service_type,
            "locators": list(op.locators),
            "provider_id": op.provider_id,
            "zk_id": op.zk_id,
            "service_note_id": op.service_note_id,
        }
    if isinstance(op, SDPWithdrawOpSerializer):
        return {
            "type": "SDPWithdraw",
            "declaration_id": op.declaration_id,
            "nonce": op.nonce,
            "service_note_id": op.service_note_id,
        }
    if isinstance(op, SDPActiveOpSerializer):
        return {
            "type": "SDPActive",
            "declaration_id": op.declaration_id,
            "nonce": op.nonce,
            "metadata": op.metadata,
        }
    if isinstance(op, LeaderClaimOpSerializer):
        return {
            "type": "LeaderClaim",
            "rewards_root": op.rewards_root,
            "voucher_nullifier": op.voucher_nullifier,
            "pk": op.pk,
        }
    if isinstance(op, ClaimPowRewardOpSerializer):
        return {
            "type": "ClaimPowReward",
            "epoch_nonce": op.epoch_nonce,
            "block_hash": op.block_hash,
            "public_key": op.public_key,
        }
    if isinstance(op, UnknownOpSerializer):
        return {
            "type": "UnknownOp",
            "opcode": op.opcode,
            "raw_payload": op.payload,
        }
    raise ValueError(f"Unsupported mantle op type: {type(op).__name__}")


class SignedTransactionSerializer(NbeSerializer, FromRandom):
    transaction: TransactionSerializer = Field(alias="mantle_tx", description="Transaction.")
    operations_proofs: List[OperationProofSerializerField] = Field(
        alias="ops_proofs",
        description="List of OperationProof. Order should match `Self::transaction::ops`.",
    )

    def _compute_hash(self) -> bytes:
        # Prefer the canonical hash reported by the node (newer nodes include it
        # in mantle_tx). A locally computed JSON hash will NOT match the chain's
        # real tx hash, so it is only a last-resort fallback for older nodes.
        if self.transaction.hash is not None:
            return self.transaction.hash
        data = self.transaction.model_dump(mode="json", exclude={"hash"})
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).digest()

    def into_transaction(self) -> Transaction:
        ops = self.transaction.ops
        if len(ops) != len(self.operations_proofs):
            raise ValueError(
                f"Number of ops ({len(ops)}) does not match number of op proofs " f"({len(self.operations_proofs)})."
            )

        operations: List[dict] = [
            {"content": _op_to_content(op), "proof": _proof_to_internal(proof)}
            for op, proof in zip(ops, self.operations_proofs)
        ]

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
