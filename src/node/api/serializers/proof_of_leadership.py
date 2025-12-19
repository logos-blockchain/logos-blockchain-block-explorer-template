from abc import ABC, abstractmethod
from typing import Annotated, Optional, Self, Union

from pydantic import BeforeValidator, Field
from rusty_results import Option

from core.models import NbeSerializer
from models.header.proof_of_leadership import (
    Groth16ProofOfLeadership,
    ProofOfLeadership,
)
from node.api.serializers.fields import BytesFromHex, BytesFromIntArray
from node.api.serializers.public import PublicSerializer
from utils.protocols import EnforceSubclassFromRandom
from utils.random import random_bytes


class ProofOfLeadershipSerializer(NbeSerializer, EnforceSubclassFromRandom, ABC):
    @abstractmethod
    def into_proof_of_leadership(self) -> ProofOfLeadership:
        raise NotImplementedError


class Groth16LeaderProofSerializer(ProofOfLeadershipSerializer, NbeSerializer):
    proof: BytesFromIntArray = Field(description="Bytes in Integer Array format (128 bytes).")
    entropy_contribution: BytesFromHex = Field(description="Fr integer in hex.")
    leader_key: BytesFromHex = Field(description="Ed25519PublicKey in hex.")
    voucher_cm: BytesFromHex = Field(description="VoucherCm hash in hex.")
    public: Optional[PublicSerializer] = Field(default=None, description="Only received if Node is running in dev mode.")

    def into_proof_of_leadership(self) -> ProofOfLeadership:
        public = self.public.into_public() if self.public else None
        return Groth16ProofOfLeadership.model_validate(
            {
                "entropy_contribution": self.entropy_contribution,
                "leader_key": self.leader_key,
                "proof": self.proof,
                "public": public,
                "voucher_cm": self.voucher_cm,
            }
        )

    @classmethod
    def from_random(cls, *, slot: Option[int]) -> Self:
        return cls.model_validate(
            {
                "proof": list(random_bytes(128)),
                "entropy_contribution": random_bytes(32).hex(),
                "leader_key": random_bytes(32).hex(),
                "voucher_cm": random_bytes(32).hex(),
                "public": PublicSerializer.from_random(slot),
            }
        )


# Fake Variant that never resolves to allow union type checking to work
def _always_fail(_):
    raise ValueError("Never matches.")


_NeverType = Annotated[object, BeforeValidator(_always_fail)]

ProofOfLeadershipVariants = Union[
    Groth16LeaderProofSerializer, _NeverType
]  # TODO: Remove _NeverType when another Variant is added
ProofOfLeadershipSerializerField = Annotated[ProofOfLeadershipVariants, Field(union_mode="left_to_right")]