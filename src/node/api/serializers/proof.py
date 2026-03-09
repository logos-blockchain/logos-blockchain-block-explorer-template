from abc import ABC, abstractmethod
from typing import Annotated, Any, Literal, Self, Union

from pydantic import BeforeValidator, Field, RootModel

from core.models import NbeSerializer
from models.transactions.operations.proofs import (
    Ed25519Signature,
    NbeSignature,
    NoProof,
    ZkAndEd25519Signature,
    ZkSignature,
)
from node.api.serializers.fields import BytesFromIntArray
from utils.protocols import EnforceSubclassFromRandom
from utils.random import random_bytes


class OperationProofSerializer(EnforceSubclassFromRandom, ABC):
    @abstractmethod
    def into_operation_proof(cls) -> NbeSignature:
        raise NotImplementedError


class NoProofSerializer(OperationProofSerializer):
    root: Literal["NoProof"]

    def into_operation_proof(self) -> NbeSignature:
        return NoProof.model_validate({})


class Ed25519SignatureSerializer(OperationProofSerializer, RootModel[bytes]):
    root: BytesFromIntArray

    def into_operation_proof(self) -> NbeSignature:
        return Ed25519Signature.model_validate(
            {
                "signature": self.root,
            }
        )

    @classmethod
    def from_random(cls, *args, **kwargs) -> Self:
        return cls.model_validate(list(random_bytes(64)))


class ZkSignatureSerializer(OperationProofSerializer, RootModel[bytes]):
    root: BytesFromIntArray

    def into_operation_proof(self) -> NbeSignature:
        return ZkSignature.model_validate(
            {
                "signature": self.root,
            }
        )

    @classmethod
    def from_random(cls, *args, **kwargs) -> Self:
        return cls.model_validate(list(random_bytes(32)))


class ZkAndEd25519SignaturesSerializer(OperationProofSerializer, NbeSerializer):
    zk_signature: BytesFromIntArray = Field(alias="zk_sig")
    ed25519_signature: BytesFromIntArray = Field(alias="ed25519_sig")

    def into_operation_proof(self) -> NbeSignature:
        return ZkAndEd25519Signature.model_validate(
            {
                "zk_signature": self.zk_signature,
                "ed25519_signature": self.ed25519_signature,
            }
        )

    @classmethod
    def from_random(cls, *args, **kwargs) -> Self:
        return ZkAndEd25519SignaturesSerializer.model_validate(
            {
                "zk_sig": list(random_bytes(32)),
                "ed25519_sig": list(random_bytes(64)),
            }
        )


PROOF_TAG_TO_SERIALIZER = {
    "NoProof": NoProofSerializer,
    "Ed25519Sig": Ed25519SignatureSerializer,
    "ZkSig": ZkSignatureSerializer,
    "ZkAndEd25519Sigs": ZkAndEd25519SignaturesSerializer,
}


def _parse_proof(data: Any) -> OperationProofSerializer:
    if isinstance(data, OperationProofSerializer):
        return data
    if isinstance(data, dict):
        for tag, serializer_class in PROOF_TAG_TO_SERIALIZER.items():
            if tag in data:
                return serializer_class.model_validate(data[tag])
    return data


OperationProofSerializerVariants = Union[
    NoProof, Ed25519SignatureSerializer, ZkSignatureSerializer, ZkAndEd25519SignaturesSerializer
]
OperationProofSerializerField = Annotated[
    OperationProofSerializerVariants,
    BeforeValidator(_parse_proof),
]
