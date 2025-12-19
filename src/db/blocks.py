import logging
from asyncio import sleep
from typing import AsyncIterator, List

from rusty_results import Empty, Option, Some
from sqlalchemy import Result, Select
from sqlalchemy.orm import aliased
from sqlmodel import select

from db.clients import DbClient
from models.block import Block


def get_latest_statement(limit: int, *, output_ascending: bool = True) -> Select:
    # Fetch the latest N blocks in descending slot order
    base = select(Block).order_by(Block.slot.desc(), Block.id.desc()).limit(limit)
    if not output_ascending:
        return base

    # Reorder for output
    inner = base.subquery()
    latest = aliased(Block, inner)
    return select(latest).options().order_by(latest.slot.asc(), latest.id.asc())  # type: ignore[arg-type]


class BlockRepository:
    """
    FIXME: Assumes slots are sequential and one block per slot
    """

    def __init__(self, client: DbClient):
        self.client = client

    async def create(self, *blocks: Block) -> None:
        with self.client.session() as session:
            session.add_all(list(blocks))
            session.commit()

    async def get_by_id(self, block_id: int) -> Option[Block]:
        statement = select(Block).where(Block.id == block_id)

        with self.client.session() as session:
            result: Result[Block] = session.exec(statement)
            if (block := result.one_or_none()) is not None:
                return Some(block)
            else:
                return Empty()

    async def get_by_hash(self, block_hash: bytes) -> Option[Block]:
        statement = select(Block).where(Block.hash == block_hash)

        with self.client.session() as session:
            result: Result[Block] = session.exec(statement)
            if (block := result.one_or_none()) is not None:
                return Some(block)
            else:
                return Empty()

    async def get_latest(self, limit: int, *, ascending: bool = True) -> List[Block]:
        if limit == 0:
            return []

        statement = get_latest_statement(limit, output_ascending=ascending)

        with self.client.session() as session:
            results: Result[Block] = session.exec(statement)
            b = results.all()
            return b

    async def get_earliest(self) -> Option[Block]:
        statement = select(Block).order_by(Block.slot.asc()).limit(1)

        with self.client.session() as session:
            results: Result[Block] = session.exec(statement)
            if (block := results.one_or_none()) is not None:
                return Some(block)
            else:
                return Empty()

    async def updates_stream(
        self, block_from: Option[Block], *, timeout_seconds: int = 1
    ) -> AsyncIterator[List[Block]]:
        slot_cursor: int = block_from.map(lambda block: block.slot).unwrap_or(0)
        id_cursor: int = block_from.map(lambda block: block.id + 1).unwrap_or(0)

        while True:
            statement = (
                select(Block)
                .where(Block.slot >= slot_cursor, Block.id >= id_cursor)
                .order_by(Block.slot.asc(), Block.id.asc())
            )

            with self.client.session() as session:
                blocks: List[Block] = session.exec(statement).all()

            if len(blocks) > 0:
                slot_cursor = blocks[-1].slot
                id_cursor = blocks[-1].id + 1
                yield blocks
            else:
                await sleep(timeout_seconds)
