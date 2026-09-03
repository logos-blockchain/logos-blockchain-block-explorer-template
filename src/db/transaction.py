from asyncio import sleep
from typing import AsyncIterator, List, Optional
from sqlalchemy import Result, Select, String, cast, func as sa_func
from sqlalchemy.orm import aliased, selectinload
from sqlmodel import select

from db.blocks import chain_block_ids_cte
from db.clients import DbClient
from models.block import Block
from models.transactions.transaction import Transaction


def get_latest_statement(limit: int, *, fork: int) -> Select:
    """The newest `limit` transactions on the fork's chain, returned oldest-first with their block loaded."""
    chain = chain_block_ids_cte(fork=fork)
    newest = (
        select(Transaction, Block.height.label("block__height"))
        .join(Block, Transaction.block_id == Block.id)
        .join(chain, Block.id == chain.c.id)
        .order_by(Block.height.desc(), Transaction.id.desc())
        .limit(limit)
        .subquery()
    )
    latest = aliased(Transaction, newest)
    return select(latest).options(selectinload(latest.block)).order_by(newest.c.block__height.asc(), latest.id.asc())


class TransactionRepository:
    def __init__(self, client: DbClient):
        self.client = client

    async def get_by_hash(self, transaction_hash: bytes, *, fork: int) -> Optional[Transaction]:
        chain = chain_block_ids_cte(fork=fork)
        statement = (
            select(Transaction)
            .join(Block, Transaction.block_id == Block.id)
            .join(chain, Block.id == chain.c.id)
            .where(Transaction.hash == transaction_hash)
        )

        with self.client.session() as session:
            result: Result[Transaction] = session.exec(statement)
            return result.first()

    async def get_latest(self, limit: int, *, fork: int) -> List[Transaction]:
        if limit == 0:
            return []

        with self.client.session() as session:
            results: Result[Transaction] = session.exec(get_latest_statement(limit, fork=fork))
            return results.all()

    async def search_by_note_id(self, note_id: bytes, *, fork: int, limit: int) -> List[Transaction]:
        """
        Transactions whose operations JSON contains the note id's hex, newest first.

        This is a textual prefilter: the hex could in principle appear in a
        non-note field (signature, public key, metadata), so callers must
        verify which operations actually reference the note.
        """
        chain = chain_block_ids_cte(fork=fork)
        statement = (
            select(Transaction)
            .options(selectinload(Transaction.block))
            .join(Block, Transaction.block_id == Block.id)
            .join(chain, Block.id == chain.c.id)
            .where(cast(Transaction.operations, String).like(f"%{note_id.hex()}%"))
            .order_by(Block.height.desc(), Transaction.id.desc())
            .limit(limit)
        )

        with self.client.session() as session:
            results: Result[Transaction] = session.exec(statement)
            return results.all()

    async def get_paginated(self, page: int, page_size: int, *, fork: int) -> tuple[List[Transaction], int]:
        """
        Get transactions with pagination, ordered by block height descending (newest first).
        Follows the chain from the fork's tip back to genesis across fork boundaries.
        Returns a tuple of (transactions, total_count).
        """
        offset = page * page_size
        chain = chain_block_ids_cte(fork=fork)

        with self.client.session() as session:
            count_statement = (
                select(sa_func.count())
                .select_from(Transaction)
                .join(Block, Transaction.block_id == Block.id)
                .join(chain, Block.id == chain.c.id)
            )
            total_count = session.exec(count_statement).one()

            statement = (
                select(Transaction)
                .options(selectinload(Transaction.block))
                .join(Block, Transaction.block_id == Block.id)
                .join(chain, Block.id == chain.c.id)
                .order_by(Block.height.desc(), Transaction.id.desc())
                .offset(offset)
                .limit(page_size)
            )
            transactions = session.exec(statement).all()

        return transactions, total_count

    async def updates_stream(
        self, transaction_from: Optional[Transaction], *, fork: int, timeout_seconds: int = 1
    ) -> AsyncIterator[List[Transaction]]:
        height_cursor = transaction_from.block.height if transaction_from is not None else 0
        transaction_id_cursor = transaction_from.id + 1 if transaction_from is not None else 0

        while True:
            statement = (
                select(Transaction)
                .options(selectinload(Transaction.block))
                .join(Block, Transaction.block_id == Block.id)
                .where(
                    Block.fork == fork,
                    Block.height >= height_cursor,
                    Transaction.id >= transaction_id_cursor,
                )
                .order_by(Block.height.asc(), Transaction.id.asc())
            )

            with self.client.session() as session:
                transactions: List[Transaction] = session.exec(statement).all()

            if len(transactions) > 0:
                height_cursor = transactions[-1].block.height
                transaction_id_cursor = transactions[-1].id + 1
                yield transactions
            else:
                await sleep(timeout_seconds)
