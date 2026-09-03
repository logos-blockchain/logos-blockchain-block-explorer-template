from abc import ABC, abstractmethod
from typing import Annotated, Any, Optional, Union

from pydantic import BeforeValidator, Field, RootModel

from core.models import NbeSerializer
from models.transactions.operations.proofs import (
    ChannelMultiSignature,
    Ed25519Signature,
    NbeSignature,
    NoneProof,
    PoCSignature,
    UnknownSignature,
    ZkAndEd25519Signature,
    ZkSignature,
)
from node.api.serializers.fields import BytesFromHex, BytesFromHexOrIntArray


class OperationProofSerializer(ABC):
    @abstractmethod
    def into_operation_proof(cls) -> NbeSignature:
        raise NotImplementedError


class Ed25519SignatureSerializer(OperationProofSerializer, RootModel[bytes]):
    root: BytesFromHexOrIntArray

    def into_operation_proof(self) -> NbeSignature:
        return Ed25519Signature.model_validate(
            {
                "signature": self.root,
            }
        )


class ZkSignatureSerializer(OperationProofSerializer, NbeSerializer):
    """Groth16 ZK proof: pi_a (32B) + pi_b (64B) + pi_c (32B) = 128 bytes total."""

    pi_a: BytesFromHexOrIntArray
    pi_b: BytesFromHexOrIntArray
    pi_c: BytesFromHexOrIntArray

    def to_bytes(self) -> bytes:
        return self.pi_a + self.pi_b + self.pi_c

    def into_operation_proof(self) -> NbeSignature:
        return ZkSignature.model_validate(
            {
                "signature": self.to_bytes(),
            }
        )


class ZkAndEd25519SignaturesSerializer(OperationProofSerializer, NbeSerializer):
    zk_signature: ZkSignatureSerializer = Field(alias="zk_sig")
    ed25519_signature: BytesFromHex = Field(alias="ed25519_sig")

    def into_operation_proof(self) -> NbeSignature:
        return ZkAndEd25519Signature.model_validate(
            {
                "zk_signature": self.zk_signature.to_bytes(),
                "ed25519_signature": self.ed25519_signature,
            }
        )


class PoCProofSerializer(OperationProofSerializer, NbeSerializer):
    """Groth16 leader claim (PoC) proof: 128 proof bytes."""

    proof: BytesFromHexOrIntArray

    def into_operation_proof(self) -> NbeSignature:
        return PoCSignature.model_validate({"proof": self.proof})


class IndexedSignatureSerializer(NbeSerializer):
    signature: BytesFromHexOrIntArray = Field(description="Ed25519 signature bytes.")
    channel_key_index: int = Field(description="Index into the channel's key list (u16).")


class ChannelMultiSigProofSerializer(OperationProofSerializer, NbeSerializer):
    """Multi-signature proof for channel config/withdraw/transfer ops."""

    signatures: list[IndexedSignatureSerializer]

    def into_operation_proof(self) -> NbeSignature:
        return ChannelMultiSignature.model_validate(
            {
                "signatures": [
                    {"signature": s.signature, "channel_key_index": s.channel_key_index} for s in self.signatures
                ],
            }
        )


class NoneProofSerializer(OperationProofSerializer, NbeSerializer):
    """Ops that carry no proof (node 0.3.0+: ClaimPowReward).

    Serialized by the node as `{"None": null}`; older builds used the bare
    string "NoProof".
    """

    def into_operation_proof(self) -> NbeSignature:
        return NoneProof()


class UnknownProofSerializer(OperationProofSerializer, NbeSerializer):
    """Fallback for proof variants without a typed serializer (e.g. NoProof).

    Preserves the raw value verbatim so unknown proof types never break block
    ingestion.
    """

    raw: Optional[Any] = None

    def into_operation_proof(self) -> NbeSignature:
        return UnknownSignature.model_validate({"raw": self.raw})


PROOF_TAG_TO_SERIALIZER = {
    "Ed25519Sig": Ed25519SignatureSerializer,
    "ZkSig": ZkSignatureSerializer,
    "ZkAndEd25519Sigs": ZkAndEd25519SignaturesSerializer,
    "PoC": PoCProofSerializer,
    "ChannelMultiSigProof": ChannelMultiSigProofSerializer,
}
NO_PROOF_MARKERS = ("None", "NoProof")


def _parse_proof(data: Any) -> OperationProofSerializer:
    if isinstance(data, OperationProofSerializer):
        return data
    if data is None or data in NO_PROOF_MARKERS:
        return NoneProofSerializer()
    if isinstance(data, dict):
        if len(data) == 1 and next(iter(data)) in NO_PROOF_MARKERS:
            return NoneProofSerializer()
        for tag, serializer_class in PROOF_TAG_TO_SERIALIZER.items():
            if tag in data:
                try:
                    return serializer_class.model_validate(data[tag])
                except Exception:
                    break
    # Unit variants (e.g. "NoProof") arrive as plain strings; unknown tagged
    # variants arrive as dicts that matched no known tag. Keep them verbatim.
    return UnknownProofSerializer.model_validate({"raw": data})


OperationProofSerializerVariants = Union[
    Ed25519SignatureSerializer,
    ZkSignatureSerializer,
    ZkAndEd25519SignaturesSerializer,
    PoCProofSerializer,
    ChannelMultiSigProofSerializer,
    NoneProofSerializer,
    UnknownProofSerializer,
]
OperationProofSerializerField = Annotated[
    OperationProofSerializerVariants,
    BeforeValidator(_parse_proof),
]
