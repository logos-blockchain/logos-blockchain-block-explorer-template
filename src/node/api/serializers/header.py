from pydantic import AliasChoices, Field
from core.models import LbeSerializer
from node.api.serializers.fields import BytesFromHex
from node.api.serializers.proof_of_leadership import ProofOfLeadershipSerializerField


class HeaderSerializer(LbeSerializer):
    hash: BytesFromHex = Field(alias="id", description="Block hash in hex format.")
    parent_block: BytesFromHex = Field(description="Hash in hex format.")
    slot: int = Field(description="Integer in u64 format.")
    # Node 0.3.0 renamed this to body_root (it now commits to uncle headers as
    # well as transactions); older nodes send block_root.
    block_root: BytesFromHex = Field(
        validation_alias=AliasChoices("body_root", "block_root"), description="Hash in hex format."
    )
    proof_of_leadership: ProofOfLeadershipSerializerField
