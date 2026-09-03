from pydantic import Field

from core.models import LbeSerializer
from models.header.proof_of_leadership import Groth16ProofOfLeadership, ProofOfLeadership
from node.api.serializers.fields import BytesFromHex


class Groth16LeaderProofSerializer(LbeSerializer):
    entropy_contribution: BytesFromHex = Field(description="Fr integer.")
    leader_key: BytesFromHex = Field(description="Hash in hex format.")
    proof: BytesFromHex = Field(description="Groth16 proof bytes (128B) in hex format.")
    voucher_cm: BytesFromHex = Field(description="Hash.")

    def into_proof_of_leadership(self) -> ProofOfLeadership:
        return Groth16ProofOfLeadership.model_validate(
            {
                "entropy_contribution": self.entropy_contribution,
                "leader_key": self.leader_key,
                "proof": self.proof,
                "voucher_cm": self.voucher_cm,
            }
        )


# Only one proof variant exists today. When a second one lands, turn this into a
# discriminated Union.
ProofOfLeadershipSerializerField = Groth16LeaderProofSerializer
