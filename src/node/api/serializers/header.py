from random import randint
from typing import Self

from pydantic import Field
from rusty_results import Option, Some

from core.models import NbeSerializer
from node.api.serializers.fields import BytesFromHex
from node.api.serializers.proof_of_leadership import (
    ProofOfLeadershipSerializer,
    ProofOfLeadershipSerializerField,
)
from utils.protocols import FromRandom
from utils.random import random_hash


class HeaderSerializer(NbeSerializer, FromRandom):
    hash: BytesFromHex = Field(default=b"", alias="id", description="Hash id in hex format.")
    parent_block: BytesFromHex = Field(description="Hash in hex format.")
    slot: int = Field(description="Integer in u64 format.")
    block_root: BytesFromHex = Field(description="Hash in hex format.")
    proof_of_leadership: ProofOfLeadershipSerializerField

    @classmethod
    def from_random(cls, *, slot: Option[int]) -> Self:
        return cls.model_validate(
            {
                "id": random_hash().hex(),
                "parent_block": random_hash().hex(),
                "slot": slot.unwrap_or_else(lambda: randint(0, 10_000)),
                "block_root": random_hash().hex(),
                "proof_of_leadership": ProofOfLeadershipSerializer.from_random(slot=slot),
            }
        )
