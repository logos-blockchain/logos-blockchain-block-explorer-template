from typing import List

from pydantic import Field

from core.models import NbeSerializer
from models.block import Block
from node.api.serializers.fields import BytesFromHex
from node.api.serializers.header import HeaderSerializer
from node.api.serializers.signed_transaction import SignedTransactionSerializer


class UncleSerializer(NbeSerializer):
    """An uncle reference as the node sends it: the competing block's header and its signature."""

    header: HeaderSerializer
    signature: BytesFromHex


class BlockSerializer(NbeSerializer):
    header: HeaderSerializer
    # Absent on pre-0.3.0 nodes.
    uncle_headers: List[UncleSerializer] = Field(default_factory=list)
    transactions: List[SignedTransactionSerializer]

    def into_block(self) -> Block:
        return Block.model_validate(
            {
                "hash": self.header.hash,
                "parent_block": self.header.parent_block,
                "slot": self.header.slot,
                "block_root": self.header.block_root,
                "proof_of_leadership": self.header.proof_of_leadership.into_proof_of_leadership(),
                "uncles": [
                    {
                        "hash": uncle.header.hash,
                        "parent_block": uncle.header.parent_block,
                        "slot": uncle.header.slot,
                        "block_root": uncle.header.block_root,
                        "leader_key": uncle.header.proof_of_leadership.leader_key,
                    }
                    for uncle in self.uncle_headers
                ],
                "transactions": [transaction.into_transaction() for transaction in self.transactions],
            }
        )

    def __repr__(self) -> str:
        return f"<BlockSerializer(slot={self.header.slot}, hash={self.header.hash.hex()})>"
