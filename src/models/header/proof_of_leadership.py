from enum import Enum
from typing import Optional, Union

from core.models import LbeSchema
from core.types import HexBytes


class ProofOfLeadershipType(Enum):
    GROTH16 = "GROTH16"


class LbeProofOfLeadership(LbeSchema):
    type: ProofOfLeadershipType


class Groth16ProofOfLeadership(LbeProofOfLeadership):
    type: ProofOfLeadershipType = ProofOfLeadershipType.GROTH16
    entropy_contribution: HexBytes
    leader_key: HexBytes
    proof: HexBytes
    voucher_cm: HexBytes


ProofOfLeadership = Union[Groth16ProofOfLeadership]
