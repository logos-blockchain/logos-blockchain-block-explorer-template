import logging
from typing import List, Tuple

from sqlalchemy import func as sa_func
from sqlmodel import select

from db.clients import DbClient
from models.block import Block
from models.channel_operation import ChannelOperation
from models.transactions.transaction import Transaction

logger = logging.getLogger(__name__)

ChannelOperationRow = Tuple[ChannelOperation, Transaction, Block]


class ChannelOperationRepository:
    def __init__(self, client: DbClient):
        self.client = client

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
