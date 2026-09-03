import logging
from typing import List, Tuple

from sqlalchemy import func as sa_func
from sqlmodel import select

from db.clients import DbClient
from models.block import Block
from models.channel_operation import ChannelOperation, channel_operations_of
from models.transactions.transaction import Transaction

logger = logging.getLogger(__name__)

BACKFILL_BATCH_SIZE = 2_000

ChannelOperationRow = Tuple[ChannelOperation, Transaction, Block]


class ChannelOperationRepository:
    def __init__(self, client: DbClient):
        self.client = client

    async def backfill(self, batch_size: int = BACKFILL_BATCH_SIZE) -> int:
        """Index channel operations for transactions stored before this table existed.

        New blocks write their rows in the same commit (see BlockRepository.create),
        so only transactions newer than the last indexed one need scanning. Returns
        the number of rows inserted.
        """
        inserted = 0
        with self.client.session() as session:
            cursor = session.exec(select(sa_func.max(ChannelOperation.transaction_id))).one() or 0
            while True:
                statement = (
                    select(Transaction).where(Transaction.id > cursor).order_by(Transaction.id.asc()).limit(batch_size)
                )
                transactions = session.exec(statement).all()
                if not transactions:
                    break
                rows = [row for transaction in transactions for row in channel_operations_of(transaction)]
                if rows:
                    session.add_all(rows)
                    session.commit()
                    inserted += len(rows)
                cursor = transactions[-1].id
        return inserted

    async def list_top(self, *, limit: int) -> List[Tuple[bytes, int, int]]:
        """(channel_id, op_count, last_height) for the most active channels on the canonical chain."""
        op_count = sa_func.count().label("op_count")
        last_height = sa_func.max(Block.height).label("last_height")
        statement = (
            select(ChannelOperation.channel_id, op_count, last_height)
            .join(Block, ChannelOperation.block_id == Block.id)
            .where(Block.canonical)
            .group_by(ChannelOperation.channel_id)
            .order_by(op_count.desc(), last_height.desc())
            .limit(limit)
        )
        with self.client.session() as session:
            return [tuple(row) for row in session.exec(statement).all()]

    async def count(self, channel_id: bytes) -> int:
        statement = (
            select(sa_func.count())
            .select_from(ChannelOperation)
            .join(Block, ChannelOperation.block_id == Block.id)
            .where(Block.canonical, ChannelOperation.channel_id == channel_id)
        )
        with self.client.session() as session:
            return session.exec(statement).one()

    async def get_operations(
        self, channel_id: bytes, *, newest_first: bool, offset: int = 0, limit: int
    ) -> List[ChannelOperationRow]:
        """Channel operations with their transaction and block, in chain order."""
        if newest_first:
            order = (Block.height.desc(), Transaction.id.desc(), ChannelOperation.op_index.desc())
        else:
            order = (Block.height.asc(), Transaction.id.asc(), ChannelOperation.op_index.asc())
        statement = (
            select(ChannelOperation, Transaction, Block)
            .join(Transaction, ChannelOperation.transaction_id == Transaction.id)
            .join(Block, ChannelOperation.block_id == Block.id)
            .where(Block.canonical, ChannelOperation.channel_id == channel_id)
            .order_by(*order)
            .offset(offset)
            .limit(limit)
        )
        with self.client.session() as session:
            return [tuple(row) for row in session.exec(statement).all()]
