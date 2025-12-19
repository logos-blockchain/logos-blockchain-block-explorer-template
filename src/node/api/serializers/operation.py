from abc import ABC, abstractmethod
from enum import IntEnum
from random import choice, randint
from typing import Annotated, Any, Dict, List, Optional, Self, Union

from pydantic import Field, model_validator

from core.models import NbeSerializer
from models.transactions.operations.contents import (
    ChannelBlob,
    ChannelInscribe,
    ChannelSetKeys,
    LeaderClaim,
    NbeContent,
    SDPActive,
    SDPDeclare,
    SDPWithdraw,
)
from node.api.serializers.fields import BytesFlexible, BytesFromHex, BytesFromInt, BytesFromIntArray
from utils.protocols import EnforceSubclassFromRandom
from utils.random import random_bytes


class OperationContentSerializer(NbeSerializer, EnforceSubclassFromRandom, ABC):
    @abstractmethod
    def into_operation_content(self) -> NbeContent:
        raise NotImplementedError


class ChannelInscribeSerializer(OperationContentSerializer):
    channel_id: BytesFlexible = Field(description="Bytes as hex or 32-integer array.")
    inscription: BytesFlexible = Field(description="Bytes as hex or integer array.")
    parent: BytesFlexible = Field(description="Bytes as hex or 32-integer array.")
    signer: BytesFromHex = Field(description="Public Key in hex format.")

    def into_operation_content(self) -> ChannelInscribe:
        return ChannelInscribe.model_validate(
            {
                "channel_id": self.channel_id,
                "inscription": self.inscription,
                "parent": self.parent,
                "signer": self.signer,
            }
        )

    @classmethod
    def from_random(cls) -> Self:
        return cls.model_validate(
            {
                "channel_id": list(random_bytes(32)),
                "inscription": list(random_bytes(32)),
                "parent": list(random_bytes(32)),
                "signer": random_bytes(32).hex(),
            }
        )


class ChannelBlobSerializer(OperationContentSerializer):
    channel: BytesFlexible = Field(description="Bytes as hex or 32-integer array.")
    blob: BytesFlexible = Field(description="Bytes as hex or 32-integer array.")
    blob_size: int
    da_storage_gas_price: int
    parent: BytesFlexible = Field(description="Bytes as hex or 32-integer array.")
    signer: BytesFromHex = Field(description="Public Key in hex format.")

    def into_operation_content(self) -> ChannelBlob:
        return ChannelBlob.model_validate(
            {
                "channel": self.channel,
                "blob": self.blob,
                "blob_size": self.blob_size,
                "da_storage_gas_price": self.da_storage_gas_price,
                "parent": self.parent,
                "signer": self.signer,
            }
        )

    @classmethod
    def from_random(cls) -> Self:
        return cls.model_validate(
            {
                "channel": list(random_bytes(32)),
                "blob": list(random_bytes(32)),
                "blob_size": randint(1, 1_024),
                "da_storage_gas_price": randint(1, 10_000),
                "parent": list(random_bytes(32)),
                "signer": random_bytes(32).hex(),
            }
        )


class ChannelSetKeysSerializer(OperationContentSerializer):
    channel: BytesFlexible = Field(description="Bytes as hex or 32-integer array.")
    keys: List[BytesFromHex] = Field(description="List of Public Keys in hex format.")

    def into_operation_content(self) -> ChannelSetKeys:
        return ChannelSetKeys.model_validate(
            {
                "channel": self.channel,
                "keys": self.keys,
            }
        )

    @classmethod
    def from_random(cls) -> Self:
        n = 1 if randint(0, 1) <= 0.5 else randint(1, 5)
        return cls.model_validate(
            {
                "channel": list(random_bytes(32)),
                "keys": [random_bytes(32).hex() for _ in range(n)],
            }
        )


class SDPDeclareServiceType(IntEnum):
    BN = 0
    DA = 1


class SDPDeclareSerializer(OperationContentSerializer):
    service_type: SDPDeclareServiceType
    locators: List[BytesFromHex]
    provider_id: BytesFromIntArray = Field(description="Bytes as an integer array.")
    zk_id: BytesFromHex = Field(description="Fr integer.")
    locked_note_id: BytesFromHex = Field(description="Fr integer.")

    def into_operation_content(self) -> SDPDeclare:
        return SDPDeclare.model_validate(
            {
                "service_type": self.service_type.name,
                "locators": self.locators,
                "provider_id": self.provider_id,
                "zk_id": self.zk_id,
                "locked_note_id": self.locked_note_id,
            }
        )

    @classmethod
    def from_random(cls) -> Self:
        n = 1 if randint(0, 1) <= 0.5 else randint(1, 5)
        return cls.model_validate(
            {
                "service_type": choice(list(SDPDeclareServiceType)),
                "locators": [random_bytes(32).hex() for _ in range(n)],
                "provider_id": list(random_bytes(32)),
                "zk_id": random_bytes(32).hex(),
                "locked_note_id": random_bytes(32).hex(),
            }
        )


class SDPWithdrawSerializer(OperationContentSerializer):
    declaration_id: BytesFromIntArray = Field(description="Bytes as a 32-integer array.")
    nonce: BytesFromInt

    def into_operation_content(self) -> SDPWithdraw:
        return SDPWithdraw.model_validate(
            {
                "declaration_id": self.declaration_id,
                "nonce": self.nonce,
            }
        )

    @classmethod
    def from_random(cls) -> Self:
        return cls.model_validate(
            {
                "declaration_id": list(random_bytes(32)),
                "nonce": int.from_bytes(random_bytes(8)),
            }
        )


class SDPActiveSerializer(OperationContentSerializer):
    declaration_id: BytesFromIntArray = Field(description="Bytes as a 32-integer array.")
    nonce: BytesFromInt
    metadata: Optional[BytesFromIntArray] = Field(default=None, description="Bytes as an integer array.")

    def into_operation_content(self) -> SDPActive:
        return SDPActive.model_validate(
            {
                "declaration_id": self.declaration_id,
                "nonce": self.nonce,
                "metadata": self.metadata,
            }
        )

    @classmethod
    def from_random(cls) -> Self:
        return cls.model_validate(
            {
                "declaration_id": list(random_bytes(32)),
                "nonce": int.from_bytes(random_bytes(8)),
                "metadata": None if randint(0, 1) <= 0.5 else list(random_bytes(32)),
            }
        )


class LeaderClaimSerializer(OperationContentSerializer):
    rewards_root: BytesFromInt = Field(description="Fr integer.")
    voucher_nullifier: BytesFromInt = Field(description="Fr integer.")
    mantle_tx_hash: BytesFromInt = Field(description="Fr integer.")

    def into_operation_content(self) -> LeaderClaim:
        return LeaderClaim.model_validate(
            {
                "rewards_root": self.rewards_root,
                "voucher_nullifier": self.voucher_nullifier,
                "mantle_tx_hash": self.mantle_tx_hash,
            }
        )

    @classmethod
    def from_random(cls) -> Self:
        return cls.model_validate(
            {
                "rewards_root": int.from_bytes(random_bytes(8)),
                "voucher_nullifier": int.from_bytes(random_bytes(8)),
                "mantle_tx_hash": int.from_bytes(random_bytes(8)),
            }
        )


class OpCode(IntEnum):
    ChannelInscribe = 0
    ChannelBlob = 1
    ChannelSetKeys = 2
    SDPDeclare = 3
    SDPWithdraw = 4
    SDPActive = 5
    LeaderClaim = 6


# Map opcode to serializer class
OPCODE_TO_SERIALIZER: Dict[int, type[OperationContentSerializer]] = {
    OpCode.ChannelInscribe: ChannelInscribeSerializer,
    OpCode.ChannelBlob: ChannelBlobSerializer,
    OpCode.ChannelSetKeys: ChannelSetKeysSerializer,
    OpCode.SDPDeclare: SDPDeclareSerializer,
    OpCode.SDPWithdraw: SDPWithdrawSerializer,
    OpCode.SDPActive: SDPActiveSerializer,
    OpCode.LeaderClaim: LeaderClaimSerializer,
}


class OperationWrapper(NbeSerializer):
    """Wrapper for operations with opcode and payload structure."""
    opcode: int
    payload: Dict[str, Any]
    
    _content: Optional[OperationContentSerializer] = None

    @model_validator(mode="after")
    def parse_payload(self) -> Self:
        serializer_cls = OPCODE_TO_SERIALIZER.get(self.opcode)
        if serializer_cls is None:
            raise ValueError(f"Unknown opcode: {self.opcode}")
        self._content = serializer_cls.model_validate(self.payload)
        return self

    def into_operation_content(self) -> NbeContent:
        if self._content is None:
            raise ValueError("Content not parsed")
        return self._content.into_operation_content()

    @classmethod
    def from_random(cls) -> Self:
        opcode = choice(list(OpCode))
        serializer_cls = OPCODE_TO_SERIALIZER[opcode]
        content = serializer_cls.from_random()
        return cls.model_validate({
            "opcode": opcode,
            "payload": content.model_dump(),
        })


type OperationContentSerializerVariants = Union[
    ChannelInscribeSerializer,
    ChannelBlobSerializer,
    ChannelSetKeysSerializer,
    SDPDeclareSerializer,
    SDPWithdrawSerializer,
    SDPActiveSerializer,
    LeaderClaimSerializer,
]
OperationContentSerializerField = Annotated[OperationContentSerializerVariants, Field(union_mode="left_to_right")]