"""Shapes served by the API. Kept separate from the stored models so the wire format is explicit."""

from typing import List, Self

from core.models import NbeSchema
from core.types import HexBytes
from models.block import Block
from models.header.proof_of_leadership import ProofOfLeadership
from models.header.uncle import UncleHeader
from models.transactions.operations.operation import Operation
from models.transactions.transaction import Transaction


class BlockSummary(NbeSchema):
    """Block row for lists and the live stream: no proof, transaction count only."""

    id: int
    hash: HexBytes
    parent_block_hash: HexBytes
    slot: int
    height: int
    block_root: HexBytes
    transaction_count: int
    uncle_count: int

    @classmethod
    def from_block(cls, block: Block) -> Self:
        return cls(
            id=block.id,
            hash=block.hash,
            parent_block_hash=block.parent_block,
            slot=block.slot,
            height=block.height,
            block_root=block.block_root,
            transaction_count=len(block.transactions),
            uncle_count=len(block.uncles),
        )


class BlockRead(NbeSchema):
    id: int
    hash: HexBytes
    parent_block_hash: HexBytes
    slot: int
    height: int
    canonical: bool
    block_root: HexBytes
    proof_of_leadership: ProofOfLeadership
    uncles: List[UncleHeader]
    transactions: List[Transaction]

    @classmethod
    def from_block(cls, block: Block) -> Self:
        return cls(
            id=block.id,
            hash=block.hash,
            parent_block_hash=block.parent_block,
            slot=block.slot,
            height=block.height,
            canonical=block.canonical,
            block_root=block.block_root,
            proof_of_leadership=block.proof_of_leadership,
            uncles=block.uncles,
            transactions=block.transactions,
        )


class TransactionRead(NbeSchema):
    id: int
    block_hash: HexBytes
    hash: HexBytes
    # False when the only copy of this transaction sits in an orphaned block.
    canonical: bool
    operations: List[Operation]

    @classmethod
    def from_pair(cls, transaction: Transaction, block: Block) -> Self:
        return cls(
            id=transaction.id,
            block_hash=block.hash,
            hash=transaction.hash,
            canonical=block.canonical,
            operations=transaction.operations,
        )
