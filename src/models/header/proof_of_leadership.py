from enum import Enum
from typing import Optional, Union

from core.models import NbeSchema
from core.types import HexBytes


class ProofOfLeadershipType(Enum):
    GROTH16 = "GROTH16"


class NbeProofOfLeadership(NbeSchema):
    type: ProofOfLeadershipType


class Groth16ProofOfLeadership(NbeProofOfLeadership):
    type: ProofOfLeadershipType = ProofOfLeadershipType.GROTH16
    entropy_contribution: HexBytes
    leader_key: HexBytes
    proof: HexBytes
    voucher_cm: HexBytes


ProofOfLeadership = Union[Groth16ProofOfLeadership]
