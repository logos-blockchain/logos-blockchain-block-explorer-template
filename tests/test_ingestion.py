"""Tests for the node ingestion loop: chain-walk backfill and stream reconnects.

A fake node serves blocks from a dict and streams from a list of scripted
stream sessions, so the loop's behaviour on stream failure is observable.
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List

import pytest

import node.lifespan as lifespan
from core.notifier import ChainNotifier
from db.blocks import BlockRepository
from db.clients.sqlite import SqliteClient
from node.api.serializers.block import BlockSerializer

FIXTURES = Path(__file__).parent / "fixtures"
TEMPLATE = json.loads((FIXTURES / "block_new_format.json").read_text())


def block_payload(hash: str, parent: str, slot: int, uncles: List[dict] | None = None) -> dict:
    """A node block payload derived from the real fixture, with its identity replaced."""
    payload = json.loads(json.dumps(TEMPLATE))
    payload["header"]["id"] = hash
    payload["header"]["parent_block"] = parent
    payload["header"]["slot"] = slot
    payload["transactions"] = []
    payload["uncle_headers"] = [{"header": uncle["header"], "signature": "cd" * 64} for uncle in (uncles or [])]
    return payload


def chain(n: int) -> Dict[str, dict]:
    """genesis child (slot 1) .. block n, keyed by hash; genesis itself is not served."""
    blocks = {}
    parent = "00" * 32
    for i in range(1, n + 1):
        h = f"{i:02x}" * 32
        blocks[h] = block_payload(h, parent, i)
        parent = h
    return blocks


class FakeNodeApi:
    def __init__(self, blocks: Dict[str, dict], stream_sessions: List[List[str]] | None = None, lib_slot: int = 0):
        self.blocks = blocks
        self.stream_sessions = list(stream_sessions or [])
        self.fetches: List[str] = []
        self.lib_slot = lib_slot

    async def get_info(self):
        tip = max(self.blocks.values(), key=lambda payload: payload["header"]["slot"])["header"]["id"]
        return SimpleNamespace(lib=tip, tip=tip, slot=len(self.blocks), height=len(self.blocks), lib_slot=self.lib_slot)

    async def get_block_by_hash(self, block_hash: str):
        self.fetches.append(block_hash)
        payload = self.blocks.get(block_hash)
        return BlockSerializer.model_validate(payload) if payload else None

    async def get_blocks_stream(self):
        if not self.stream_sessions:
            raise ConnectionError("node down")
        session = self.stream_sessions.pop(0)
        for block_hash in session:
            yield BlockSerializer.model_validate(self.blocks[block_hash])
        # returning ends the stream, as a node restart would


@pytest.fixture
def app(tmp_path):
    client = SqliteClient(sqlite_db_path=f"sqlite:///{tmp_path / 'test.db'}")
    return SimpleNamespace(
        state=SimpleNamespace(
            block_repository=BlockRepository(client),
            chain_notifier=ChainNotifier(),
            node_api=None,
        )
    )


def stored_heights(app) -> List[int]:
    return [b.height for b in asyncio.run(app.state.block_repository.get_latest(1000))]


def stored(app, hash: str):
    return asyncio.run(app.state.block_repository.get_by_hash(bytes.fromhex(hash)))


def test_backfill_stores_referenced_uncles_including_uncle_chains(app):
    blocks = chain(5)
    # Uncle U1 competes with block 3 (parent = block 2); U2 builds on U1. Block 5 references both.
    u1 = block_payload("a1" * 32, "02" * 32, 3)
    u2 = block_payload("a2" * 32, "a1" * 32, 4)
    blocks["a1" * 32] = u1
    blocks["a2" * 32] = u2
    blocks["05" * 32] = block_payload("05" * 32, "04" * 32, 5, uncles=[u2, u1])
    app.state.node_api = FakeNodeApi(blocks)

    asyncio.run(lifespan.backfill_to_lib(app))

    assert stored_heights(app) == list(range(1, 6))  # canonical chain unaffected
    assert (stored(app, "a1" * 32).height, stored(app, "a1" * 32).canonical) == (3, False)
    assert (stored(app, "a2" * 32).height, stored(app, "a2" * 32).canonical) == (4, False)


def test_uncles_below_lib_are_not_probed(app):
    # The node prunes non-canonical blocks behind the LIB, so asking for them is pointless.
    blocks = chain(5)
    old_uncle = block_payload("a1" * 32, "01" * 32, 2)  # slot 2, below LIB
    new_uncle = block_payload("a2" * 32, "03" * 32, 4)  # slot 4, at/above LIB
    blocks["05" * 32] = block_payload("05" * 32, "04" * 32, 5, uncles=[old_uncle, new_uncle])
    blocks["a2" * 32] = new_uncle  # the node still has the recent one, and has pruned the old one
    app.state.node_api = FakeNodeApi(blocks, lib_slot=4)

    asyncio.run(lifespan.backfill_to_lib(app))

    assert "a1" * 32 not in app.state.node_api.fetches
    assert stored(app, "a2" * 32).canonical is False


def test_streamed_block_backfills_its_uncles(app):
    blocks = chain(3)
    app.state.node_api = FakeNodeApi(blocks)
    asyncio.run(lifespan.backfill_to_lib(app))

    u = block_payload("a1" * 32, "02" * 32, 3)
    blocks["a1" * 32] = u
    blocks["04" * 32] = block_payload("04" * 32, "03" * 32, 4, uncles=[u])
    asyncio.run(lifespan.store_streamed_block(app, BlockSerializer.model_validate(blocks["04" * 32])))

    assert stored_heights(app) == [1, 2, 3, 4]
    assert stored(app, "a1" * 32).canonical is False


def test_backfill_inserts_oldest_first_in_batches_with_bounded_memory(app, monkeypatch):
    monkeypatch.setattr(lifespan, "SQLITE_BATCH_INSERT_SIZE", 4)
    blocks = chain(10)
    app.state.node_api = FakeNodeApi(blocks)

    asyncio.run(lifespan.backfill_to_lib(app))

    assert stored_heights(app) == list(range(1, 11))
    # Every block fetched once on the walk; the two newer batches (6 blocks)
    # refetched, the oldest batch served from the retained bodies.
    assert len(app.state.node_api.fetches) == 10 + 1 + 6  # +1 for the genesis miss


def test_backfill_stops_at_already_stored_block(app):
    blocks = chain(6)
    app.state.node_api = FakeNodeApi(blocks)
    asyncio.run(lifespan.backfill_to_lib(app))
    fetched_before = len(app.state.node_api.fetches)

    # Two more blocks appear; walking from the new tip stops at block 6.
    for i in (7, 8):
        h = f"{i:02x}" * 32
        blocks[h] = block_payload(h, f"{i - 1:02x}" * 32, i)
    asyncio.run(lifespan.backfill_chain_from_hash(app, "08" * 32))

    assert stored_heights(app) == list(range(1, 9))
    assert len(app.state.node_api.fetches) - fetched_before == 2


def test_subscription_reconnects_after_stream_ends_and_backfills_gap(app, monkeypatch):
    blocks = chain(3)
    app.state.node_api = FakeNodeApi(blocks)
    asyncio.run(lifespan.backfill_to_lib(app))

    for i in (4, 5, 6):
        h = f"{i:02x}" * 32
        blocks[h] = block_payload(h, f"{i - 1:02x}" * 32, i)
    # Session 1 delivers block 4 then drops. Session 2 delivers block 6 only;
    # block 5 was missed while disconnected and must come from the backfill.
    app.state.node_api.stream_sessions = [["04" * 32], ["06" * 32]]

    sleeps: List[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 3:
            raise asyncio.CancelledError  # stop the forever-loop once reconnects are proven

    monkeypatch.setattr(lifespan.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(lifespan.subscribe_to_new_blocks(app))

    assert stored_heights(app) == list(range(1, 7))
    # Backoff: 1s after session 1 ended, reset to 1s by session 2's block, then
    # doubling once the node is down for good.
    assert sleeps == [1.0, 1.0, 2.0]


def test_subscription_survives_stream_errors(app, monkeypatch):
    blocks = chain(2)
    app.state.node_api = FakeNodeApi(blocks, stream_sessions=[])  # every connect raises
    asyncio.run(lifespan.backfill_to_lib(app))

    sleeps: List[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 4:
            raise asyncio.CancelledError

    monkeypatch.setattr(lifespan.asyncio, "sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(lifespan.subscribe_to_new_blocks(app))

    assert sleeps == [1.0, 2.0, 4.0, 8.0]
