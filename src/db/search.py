"""Repository for search operations across blocks and transactions."""

from typing import Optional, Tuple

from sqlmodel import select

from db.clients import DbClient
from models.block import Block
from models.transactions.transaction import Transaction


class SearchRepository:
    """Repository for search operations across blocks and transactions."""

    def __init__(self, client: DbClient):
        self.client = client

    async def search_by_hash(self, hash_value: str) -> Optional[Tuple[str, int]]:
        """
        Search for a block or transaction by hash.

        Args:
            hash_value: Hex string hash (with or without 0x prefix)

        Returns:
            Tuple of (type, id) where type is "block" or "transaction",
            or None if not found.
        """
        # Normalize hash (handle 0x prefix)
        if hash_value.startswith("0x"):
            hash_bytes = bytes.fromhex(hash_value[2:])
        else:
            hash_bytes = bytes.fromhex(hash_value)

        with self.client.session() as session:
            # Try to find as block first
            block_result = session.exec(
                select(Block).where(Block.hash == hash_bytes)
            ).first()

            if block_result:
                return ("block", block_result.id)

            # Try to find as transaction
            tx_result = session.exec(
                select(Transaction).where(Transaction.hash == hash_bytes)
            ).first()

            if tx_result:
                return ("transaction", tx_result.id)

        return None
