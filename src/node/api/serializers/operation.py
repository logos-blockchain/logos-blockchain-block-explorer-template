from abc import ABC, abstractmethod
from enum import Enum
from random import choice, randint
from typing import Annotated, Any, List, Optional, Self, Union

from pydantic import BeforeValidator, Field

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
from node.api.serializers.fields import BytesFromHex, BytesFromInt, BytesFromIntArray
from utils.protocols import EnforceSubclassFromRandom
from utils.random import random_bytes


class OperationContentSerializer(NbeSerializer, EnforceSubclassFromRandom, ABC):
    @abstractmethod
    def into_operation_content(self) -> NbeContent:
        raise NotImplementedError


class ChannelInscribeSerializer(OperationContentSerializer):
    channel_id: BytesFromHex = Field(description="Channel ID in hex format.")
    inscription: BytesFromIntArray = Field(description="Bytes as an integer array.")
    parent: BytesFromHex = Field(description="Parent hash in hex format.")
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
                "channel_id": random_bytes(32).hex(),
                "inscription": list(random_bytes(32)),
                "parent": random_bytes(32).hex(),
                "signer": random_bytes(32).hex(),
            }
        )


class ChannelBlobSerializer(OperationContentSerializer):
    channel: BytesFromHex = Field(description="Channel ID in hex format.")
    blob: BytesFromIntArray = Field(description="Bytes as an integer array.")
    blob_size: int
    da_storage_gas_price: int
    parent: BytesFromHex = Field(description="Parent hash in hex format.")
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
                "channel": random_bytes(32).hex(),
                "blob": list(random_bytes(32)),
                "blob_size": randint(1, 1_024),
                "da_storage_gas_price": randint(1, 10_000),
                "parent": random_bytes(32).hex(),
                "signer": random_bytes(32).hex(),
            }
        )


class ChannelSetKeysSerializer(OperationContentSerializer):
    channel: BytesFromHex = Field(description="Channel ID in hex format.")
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
                "channel": random_bytes(32).hex(),
                "keys": [random_bytes(32).hex() for _ in range(n)],
            }
        )


class SDPDeclareServiceType(Enum):
    BN = "BN"
    DA = "DA"


class SDPDeclareSerializer(OperationContentSerializer):
    service_type: SDPDeclareServiceType
    locators: List[BytesFromHex]
    provider_id: BytesFromHex = Field(description="Provider ID in hex format.")
    zk_id: BytesFromHex = Field(description="Fr integer.")
    locked_note_id: BytesFromHex = Field(description="Fr integer.")

    def into_operation_content(self) -> SDPDeclare:
        return SDPDeclare.model_validate(
            {
                "service_type": self.service_type.value,
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
                "service_type": choice(list(SDPDeclareServiceType)).value,
                "locators": [random_bytes(32).hex() for _ in range(n)],
                "provider_id": random_bytes(32).hex(),
                "zk_id": random_bytes(32).hex(),
                "locked_note_id": random_bytes(32).hex(),
            }
        )


class SDPWithdrawSerializer(OperationContentSerializer):
    declaration_id: BytesFromHex = Field(description="Declaration ID in hex format.")
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
                "declaration_id": random_bytes(32).hex(),
                "nonce": int.from_bytes(random_bytes(8)),
            }
        )


class SDPActiveSerializer(OperationContentSerializer):
    declaration_id: BytesFromHex = Field(description="Declaration ID in hex format.")
    nonce: BytesFromInt
    metadata: Optional[BytesFromIntArray] = Field(description="Bytes as an integer array.")

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
                "declaration_id": random_bytes(32).hex(),
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


OPCODE_TO_SERIALIZER: dict[int, type[OperationContentSerializer]] = {
    0: ChannelInscribeSerializer,
    1: ChannelBlobSerializer,
    2: ChannelSetKeysSerializer,
    3: SDPDeclareSerializer,
    4: SDPWithdrawSerializer,
    5: SDPActiveSerializer,
    6: LeaderClaimSerializer,
}


def _parse_operation(data: Any) -> OperationContentSerializer:
    if isinstance(data, OperationContentSerializer):
        return data
    if isinstance(data, dict) and "opcode" in data:
        opcode = data["opcode"]
        payload = data["payload"]
        serializer_class = OPCODE_TO_SERIALIZER.get(opcode)
        if serializer_class is None:
            raise ValueError(f"Unknown operation opcode: {opcode}")
        return serializer_class.model_validate(payload)
    return data


type OperationContentSerializerVariants = Union[
    ChannelInscribeSerializer,
    ChannelBlobSerializer,
    ChannelSetKeysSerializer,
    SDPDeclareSerializer,
    SDPWithdrawSerializer,
    SDPActiveSerializer,
    LeaderClaimSerializer,
]
OperationContentSerializerField = Annotated[
    OperationContentSerializerVariants,
    BeforeValidator(_parse_operation),
]
