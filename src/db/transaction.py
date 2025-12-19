import logging
from asyncio import sleep
from typing import AsyncIterator, List

from rusty_results import Empty, Option, Some
from sqlalchemy import Result, Select
from sqlalchemy.orm import aliased, selectinload
from sqlmodel import select

from db.clients import DbClient
from models.block import Block
from models.transactions.transaction import Transaction


def get_latest_statement(limit: int, *, output_ascending: bool, preload_relationships: bool) -> Select:
    # Join with Block to order by Block's slot and fetch the latest N transactions in descending order
    base = (
        select(Transaction, Block.slot.label("block__slot"), Block.id.label("block__id"))
        .join(Block, Transaction.block_id == Block.id)
        .order_by(Block.slot.desc(), Block.id.desc(), Transaction.id.desc())
        .limit(limit)
    )
    if not output_ascending:
        return base

    # Reorder for output
    inner = base.subquery()
    latest = aliased(Transaction, inner)
    statement = select(latest).order_by(inner.c.block__slot.asc(), inner.c.block__id.asc(), latest.id.asc())
    if preload_relationships:
        statement = statement.options(selectinload(latest.block))
    return statement


class TransactionRepository:
    def __init__(self, client: DbClient):
        self.client = client

    async def create(self, *transaction: Transaction) -> None:
        with self.client.session() as session:
            session.add_all(list(transaction))
            session.commit()

    async def get_by_id(self, transaction_id: int) -> Option[Transaction]:
        statement = select(Transaction).where(Transaction.id == transaction_id)

        with self.client.session() as session:
            result: Result[Transaction] = session.exec(statement)
            if (transaction := result.one_or_none()) is not None:
                return Some(transaction)
            else:
                return Empty()

    async def get_by_hash(self, transaction_hash: bytes) -> Option[Transaction]:
        statement = select(Transaction).where(Transaction.hash == transaction_hash)

        with self.client.session() as session:
            result: Result[Transaction] = session.exec(statement)
            if (transaction := result.one_or_none()) is not None:
                return Some(transaction)
            else:
                return Empty()

    async def get_latest(
        self, limit: int, *, ascending: bool = False, preload_relationships: bool = False
    ) -> List[Transaction]:
        if limit == 0:
            return []

        statement = get_latest_statement(limit, output_ascending=ascending, preload_relationships=preload_relationships)

        with self.client.session() as session:
            results: Result[Transaction] = session.exec(statement)
            return results.all()

    async def updates_stream(
        self, transaction_from: Option[Transaction], *, timeout_seconds: int = 1
    ) -> AsyncIterator[List[Transaction]]:
        slot_cursor = transaction_from.map(lambda transaction: transaction.block.slot).unwrap_or(0)
        block_id_cursor = transaction_from.map(lambda transaction: transaction.block.id).unwrap_or(0)
        transaction_id_cursor = transaction_from.map(lambda transaction: transaction.id + 1).unwrap_or(0)

        while True:
            statement = (
                select(Transaction)
                .options(selectinload(Transaction.block))
                .join(Block, Transaction.block_id == Block.id)
                .where(
                    Block.slot >= slot_cursor,
                    Block.id >= block_id_cursor,
                    Transaction.id >= transaction_id_cursor,
                )
                .order_by(Block.slot.asc(), Block.id.asc(), Transaction.id.asc())
            )

            with self.client.session() as session:
                transactions: List[Transaction] = session.exec(statement).all()

            if len(transactions) > 0:
                slot_cursor = transactions[-1].block.slot
                block_id_cursor = transactions[-1].block.id
                transaction_id_cursor = transactions[-1].id + 1
                yield transactions
            else:
                await sleep(timeout_seconds)
