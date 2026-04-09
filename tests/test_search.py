"""Tests for SearchRepository."""

import tempfile
from pathlib import Path

import pytest

from db.clients.sqlite import SqliteClient
from db.search import SearchRepository
from models.block import Block


@pytest.mark.asyncio
async def test_search_by_block_hash():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"sqlite:///{Path(tmpdir) / 'test.db'}"
        client = SqliteClient(db_path)
        repo = SearchRepository(client)

        # Search for non-existent block should return None
        result = await repo.search_by_hash("0x" + "00" * 32)
        assert result is None


@pytest.mark.asyncio
async def test_search_by_transaction_hash():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"sqlite:///{Path(tmpdir) / 'test.db'}"
        client = SqliteClient(db_path)
        repo = SearchRepository(client)

        # Search for non-existent transaction should return None
        result = await repo.search_by_hash("0x" + "11" * 32)
        assert result is None


@pytest.mark.asyncio
async def test_search_finds_block():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"sqlite:///{Path(tmpdir) / 'test.db'}"
        client = SqliteClient(db_path)
        repo = SearchRepository(client)

        # Create a block
        test_hash = bytes.fromhex("aa" * 32)
        block = Block(
            hash=test_hash,
            parent_block=b"\x00" * 32,
            slot=1,
            height=0,
            block_root=b"\x00" * 32,
            proof_of_leadership=None,
        )

        with client.session() as session:
            session.add(block)
            session.flush()
            block_id = block.id
            session.commit()

        # Search for the block
        result = await repo.search_by_hash("0x" + "aa" * 32)
        assert result is not None
        assert result[0] == "block"
        assert result[1] == block_id


@pytest.mark.asyncio
async def test_search_without_0x_prefix():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"sqlite:///{Path(tmpdir) / 'test.db'}"
        client = SqliteClient(db_path)
        repo = SearchRepository(client)

        # Create a block
        test_hash = bytes.fromhex("dd" * 32)
        block = Block(
            hash=test_hash,
            parent_block=b"\x00" * 32,
            slot=1,
            height=0,
            block_root=b"\x00" * 32,
            proof_of_leadership=None,
        )

        with client.session() as session:
            session.add(block)
            session.flush()
            session.commit()

        # Search without 0x prefix
        result = await repo.search_by_hash("dd" * 32)
        assert result is not None
        assert result[0] == "block"


@pytest.mark.asyncio
async def test_search_returns_tuple_with_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"sqlite:///{Path(tmpdir) / 'test.db'}"
        client = SqliteClient(db_path)
        repo = SearchRepository(client)

        # Create a block
        test_hash = bytes.fromhex("ee" * 32)
        block = Block(
            hash=test_hash,
            parent_block=b"\x00" * 32,
            slot=1,
            height=0,
            block_root=b"\x00" * 32,
            proof_of_leadership=None,
        )

        with client.session() as session:
            session.add(block)
            session.flush()
            block_id = block.id
            session.commit()

        # Search should return tuple (type, id)
        result = await repo.search_by_hash("0x" + "ee" * 32)
        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] == "block"
        assert isinstance(result[1], int)
        assert result[1] > 0
