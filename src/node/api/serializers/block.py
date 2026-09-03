from typing import List

from core.models import NbeSerializer
from models.block import Block
from node.api.serializers.header import HeaderSerializer
from node.api.serializers.signed_transaction import SignedTransactionSerializer


class BlockSerializer(NbeSerializer):
    header: HeaderSerializer
    transactions: List[SignedTransactionSerializer]

    def into_block(self) -> Block:
        transactions = [transaction.into_transaction() for transaction in self.transactions]
        return Block.model_validate(
            {
                "hash": self.header.hash,
                "parent_block": self.header.parent_block,
                "slot": self.header.slot,
                "block_root": self.header.block_root,
                "proof_of_leadership": self.header.proof_of_leadership.into_proof_of_leadership(),
            }
        ).with_transactions(transactions)

    def __repr__(self) -> str:
        return f"<BlockSerializer(slot={self.header.slot}, hash={self.header.hash.hex()})>"
