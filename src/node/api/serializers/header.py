from enum import IntEnum
from random import randint
from typing import Optional, Self

from pydantic import Field, computed_field
from rusty_results import Option

from core.models import NbeSerializer
from node.api.serializers.fields import BytesFromHex
from node.api.serializers.proof_of_leadership import (
    ProofOfLeadershipSerializer,
    ProofOfLeadershipSerializerField,
)
from utils.protocols import FromRandom
from utils.random import random_hash


class Version(IntEnum):
    Bedrock = 1


class HeaderSerializer(NbeSerializer, FromRandom):
    id: Optional[BytesFromHex] = Field(default=None, description="Header ID hash in hex format.")
    version: Version = Field(default=Version.Bedrock, description="Block version.")
    parent_block: BytesFromHex = Field(description="Hash in hex format.")
    slot: int = Field(description="Integer in u64 format.")
    block_root: BytesFromHex = Field(description="Hash in hex format.")
    proof_of_leadership: ProofOfLeadershipSerializerField

    @computed_field
    @property
    def hash(self) -> bytes:
        """Return the header hash (id if available, otherwise block_root)."""
        return self.id if self.id is not None else self.block_root

    @classmethod
    def from_random(cls, *, slot: Option[int]) -> Self:
        return cls.model_validate(
            {
                "id": random_hash().hex(),
                "version": Version.Bedrock,
                "parent_block": random_hash().hex(),
                "slot": slot.unwrap_or_else(lambda: randint(0, 10_000)),
                "block_root": random_hash().hex(),
                "proof_of_leadership": ProofOfLeadershipSerializer.from_random(slot=slot),
            }
        )