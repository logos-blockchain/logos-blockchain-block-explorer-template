from abc import ABC, abstractmethod
from typing import Annotated, Any, Dict, Self, Union

from pydantic import Field, RootModel, model_validator

from core.models import NbeSerializer
from models.transactions.operations.proofs import (
    Ed25519Signature,
    NbeSignature,
    ZkAndEd25519Signature,
    ZkSignature,
)
from node.api.serializers.fields import BytesFromHex, BytesFromIntArray
from utils.protocols import EnforceSubclassFromRandom
from utils.random import random_bytes


class OperationProofSerializer(EnforceSubclassFromRandom, ABC):
    @abstractmethod
    def into_operation_proof(cls) -> NbeSignature:
        raise NotImplementedError


class Ed25519SignatureSerializer(OperationProofSerializer, NbeSerializer):
    """Ed25519 signature as int array, wrapped in Ed25519Sig key."""
    signature: BytesFromIntArray = Field(alias="Ed25519Sig")

    def into_operation_proof(self) -> NbeSignature:
        return Ed25519Signature.model_validate(
            {
                "signature": self.signature,
            }
        )

    @classmethod
    def from_random(cls, *args, **kwargs) -> Self:
        return cls.model_validate({"Ed25519Sig": list(random_bytes(64))})


class ZkSignatureComponentsSerializer(NbeSerializer):
    """ZK signature proof with pi_a, pi_b, pi_c components as int arrays."""
    pi_a: BytesFromIntArray = Field(description="32 bytes as int array")
    pi_b: BytesFromIntArray = Field(description="64 bytes as int array")
    pi_c: BytesFromIntArray = Field(description="32 bytes as int array")


class ZkSignatureSerializer(OperationProofSerializer, NbeSerializer):
    """ZK signature wrapped in ZkSig key."""
    zk_sig: ZkSignatureComponentsSerializer = Field(alias="ZkSig")

    def into_operation_proof(self) -> NbeSignature:
        # Concatenate the components for storage
        signature = self.zk_sig.pi_a + self.zk_sig.pi_b + self.zk_sig.pi_c
        return ZkSignature.model_validate(
            {
                "signature": signature,
            }
        )

    @classmethod
    def from_random(cls, *args, **kwargs) -> Self:
        return cls.model_validate({
            "ZkSig": {
                "pi_a": list(random_bytes(32)),
                "pi_b": list(random_bytes(64)),
                "pi_c": list(random_bytes(32)),
            }
        })


class ZkAndEd25519SignaturesSerializer(OperationProofSerializer, NbeSerializer):
    """Combined ZK and Ed25519 signatures."""
    zk_signature: ZkSignatureComponentsSerializer = Field(alias="zk_sig")
    ed25519_signature: BytesFromIntArray = Field(alias="ed25519_sig")

    def into_operation_proof(self) -> NbeSignature:
        zk_sig = self.zk_signature.pi_a + self.zk_signature.pi_b + self.zk_signature.pi_c
        return ZkAndEd25519Signature.model_validate(
            {
                "zk_signature": zk_sig,
                "ed25519_signature": self.ed25519_signature,
            }
        )

    @classmethod
    def from_random(cls, *args, **kwargs) -> Self:
        return cls.model_validate(
            {
                "zk_sig": {
                    "pi_a": list(random_bytes(32)),
                    "pi_b": list(random_bytes(64)),
                    "pi_c": list(random_bytes(32)),
                },
                "ed25519_sig": list(random_bytes(64)),
            }
        )


OperationProofSerializerVariants = Union[
    Ed25519SignatureSerializer, ZkSignatureSerializer, ZkAndEd25519SignaturesSerializer
]
OperationProofSerializerField = Annotated[OperationProofSerializerVariants, Field(union_mode="left_to_right")]