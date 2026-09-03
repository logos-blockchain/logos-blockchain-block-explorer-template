from typing import List, Optional

from sqlalchemy import Result, String, cast, func as sa_func
from sqlalchemy.orm import selectinload
from sqlmodel import select

from db.clients import DbClient
from models.block import Block
from models.transactions.transaction import Transaction


def _canonical_transactions():
    """Transactions on the canonical chain, with their block preloaded."""
    return (
        select(Transaction)
        .options(selectinload(Transaction.block))
        .join(Block, Transaction.block_id == Block.id)
        .where(Block.canonical)
    )


class TransactionRepository:
    def __init__(self, client: DbClient):
        self.client = client

    async def get_by_hash(self, transaction_hash: bytes) -> Optional[Transaction]:
        """The canonical copy if one exists, otherwise the copy from an orphaned block."""
        statement = (
            select(Transaction)
            .options(selectinload(Transaction.block))
            .join(Block, Transaction.block_id == Block.id)
            .where(Transaction.hash == transaction_hash)
            .order_by(Block.canonical.desc(), Block.height.desc())
            .limit(1)
        )
        with self.client.session() as session:
            result: Result[Transaction] = session.exec(statement)
            return result.first()

    async def get_latest(self, limit: int) -> List[Transaction]:
        """The newest `limit` canonical transactions, oldest-first."""
        if limit == 0:
            return []

        statement = _canonical_transactions().order_by(Block.height.desc(), Transaction.id.desc()).limit(limit)
        with self.client.session() as session:
            return list(reversed(session.exec(statement).all()))

    async def get_since(self, canonical_seq: int, *, limit: int = 500) -> List[Transaction]:
        """Transactions whose block became canonical after stamp `canonical_seq`, in chain order."""
        statement = (
            _canonical_transactions()
            .where(Block.canonical_seq > canonical_seq)
            .order_by(Block.canonical_seq.asc(), Block.height.asc(), Transaction.id.asc())
            .limit(limit)
        )
        with self.client.session() as session:
            return session.exec(statement).all()

    async def search_by_note_id(self, note_id: bytes, *, limit: int) -> List[Transaction]:
        """
        Transactions whose operations JSON contains the note id's hex, newest first.

        This is a textual prefilter: the hex could in principle appear in a
        non-note field (signature, public key, metadata), so callers must
        verify which operations actually reference the note.
        """
        statement = (
            _canonical_transactions()
            .where(cast(Transaction.operations, String).like(f"%{note_id.hex()}%"))
            .order_by(Block.height.desc(), Transaction.id.desc())
            .limit(limit)
        )
        with self.client.session() as session:
            return session.exec(statement).all()

    async def get_paginated(self, page: int, page_size: int) -> tuple[List[Transaction], int]:
        """Canonical transactions, newest first, plus the total count."""
        offset = page * page_size

        with self.client.session() as session:
            count_statement = (
                select(sa_func.count())
                .select_from(Transaction)
                .join(Block, Transaction.block_id == Block.id)
                .where(Block.canonical)
            )
            total_count = session.exec(count_statement).one()

            statement = (
                _canonical_transactions()
                .order_by(Block.height.desc(), Transaction.id.desc())
                .offset(offset)
                .limit(page_size)
            )
            transactions = session.exec(statement).all()

        return transactions, total_count
