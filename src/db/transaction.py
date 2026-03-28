from asyncio import sleep
from typing import AsyncIterator, List, Optional

from rusty_results import Empty, Option, Some
from sqlalchemy import Result, Select, func as sa_func
from sqlalchemy.orm import aliased, selectinload
from sqlmodel import select

from db.blocks import chain_block_ids_cte
from db.clients import DbClient
from models.block import Block
from models.transactions.transaction import Transaction


def get_latest_statement(limit: int, *, fork: int, output_ascending: bool, preload_relationships: bool) -> Select:
    chain = chain_block_ids_cte(fork=fork)
    base = (
        select(Transaction, Block.height.label("block__height"))
        .join(Block, Transaction.block_id == Block.id)
        .join(chain, Block.id == chain.c.id)
        .order_by(Block.height.desc(), Transaction.id.desc())
        .limit(limit)
    )
    if not output_ascending:
        return base

    # Reorder for output
    inner = base.subquery()
    latest = aliased(Transaction, inner)
    statement = select(latest).order_by(inner.c.block__height.asc(), latest.id.asc())
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

    async def get_by_hash(self, transaction_hash: bytes, *, fork: int) -> Option[Transaction]:
        chain = chain_block_ids_cte(fork=fork)
        statement = (
            select(Transaction)
            .join(Block, Transaction.block_id == Block.id)
            .join(chain, Block.id == chain.c.id)
            .where(Transaction.hash == transaction_hash)
        )

        with self.client.session() as session:
            result: Result[Transaction] = session.exec(statement)
            if (transaction := result.first()) is not None:
                return Some(transaction)
            else:
                return Empty()

    async def get_latest(
        self, limit: int, *, fork: int, ascending: bool = False, preload_relationships: bool = False
    ) -> List[Transaction]:
        if limit == 0:
            return []

        statement = get_latest_statement(
            limit, fork=fork, output_ascending=ascending, preload_relationships=preload_relationships
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
        self, transaction_from: Option[Transaction], *, fork: int, timeout_seconds: int = 1
    ) -> AsyncIterator[List[Transaction]]:
        height_cursor = transaction_from.map(lambda transaction: transaction.block.height).unwrap_or(0)
        transaction_id_cursor = transaction_from.map(lambda transaction: transaction.id + 1).unwrap_or(0)

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

    async def search(
        self,
        query: str,
        *,
        fork: int,
        page: int = 0,
        page_size: int = 50,
    ) -> tuple[List[Transaction], int]:
        """
        Search transactions by hash, channel_id, or inscription.
        Returns (transactions, total_count).
        """
        offset = page * page_size
        chain = chain_block_ids_cte(fork=fork)

        # Build search condition: match hash, channel_id, or inscription (case-insensitive, partial)
        search_term = query.lower()

        with self.client.session() as session:
            # Get all transactions in the chain
            all_statement = (
                select(Transaction)
                .options(selectinload(Transaction.block))
                .join(Block, Transaction.block_id == Block.id)
                .join(chain, Block.id == chain.c.id)
                .order_by(Block.height.desc(), Transaction.id.desc())
            )
            all_transactions = session.exec(all_statement).all()

            # Filter in Python for hash, channel, and inscription matching
            filtered = []
            for tx in all_transactions:
                # Check hash
                hex_hash = tx.hash.hex().lower() if hasattr(tx.hash, 'hex') else bytes(tx.hash).hex().lower()
                
                # Check channel_id and inscription in operations
                channel_matches = []
                inscription_matches = []
                
                if hasattr(tx, 'operations') and tx.operations:
                    for op in tx.operations:
                        if hasattr(op, 'content') and op.content:
                            content = op.content
                            
                            # Check channel_id (from ChannelInscribe, ChannelBlob, ChannelSetKeys)
                            channel_id = content.get('channel_id') or content.get('channel')
                            if channel_id and isinstance(channel_id, str):
                                channel_id_lower = channel_id.lower()
                                if search_term in channel_id_lower:
                                    channel_matches.append(channel_id)
                            
                            # Check inscription (from ChannelInscribe)
                            inscription = content.get('inscription')
                            if inscription and isinstance(inscription, str):
                                # Check hex inscription
                                if search_term in inscription.lower():
                                    inscription_matches.append(inscription)
                                # Also check decoded text
                                try:
                                    if len(inscription) % 2 == 0:
                                        bytes_data = bytes.fromhex(inscription)
                                        decoded = bytes_data.decode('utf-8')
                                        if search_term in decoded.lower():
                                            inscription_matches.append(decoded)
                                except (ValueError, UnicodeDecodeError):
                                    pass
                
                # Add transaction if any search criteria match
                if (search_term in hex_hash or 
                    len(channel_matches) > 0 or 
                    len(inscription_matches) > 0):
                    filtered.append(tx)

            # Apply pagination
            total_count = len(filtered)
            transactions = filtered[offset:offset + page_size]

        return transactions, total_count

    async def search_by_block_height(
        self,
        block_height: int,
        *,
        fork: int,
        page: int = 0,
        page_size: int = 50,
    ) -> tuple[List[Transaction], int]:
        """
        Search transactions by block height.
        Returns (transactions, total_count).
        """
        offset = page * page_size
        chain = chain_block_ids_cte(fork=fork)

        with self.client.session() as session:
            # Count total matching transactions
            count_statement = (
                select(sa_func.count())
                .select_from(Transaction)
                .join(Block, Transaction.block_id == Block.id)
                .join(chain, Block.id == chain.c.id)
                .where(Block.height == block_height)
            )
            total_count = session.exec(count_statement).one()

            if total_count == 0:
                return [], 0

            # Get matching transactions
            statement = (
                select(Transaction)
                .options(selectinload(Transaction.block))
                .join(Block, Transaction.block_id == Block.id)
                .join(chain, Block.id == chain.c.id)
                .where(Block.height == block_height)
                .order_by(Transaction.id.desc())
                .offset(offset)
                .limit(page_size)
            )

            transactions = session.exec(statement).all()

        return transactions, total_count
