"""Tests for height assignment and canonical-chain tracking in BlockRepository.

Blocks are stored non-canonical; `set_canonical_tip` applies the node's fork
choice, which is not plain longest-chain.
"""

import asyncio
from typing import Dict

import pytest
from sqlmodel import select

from db.blocks import BlockRepository
from db.clients.sqlite import SqliteClient
from models.block import Block
from models.header.proof_of_leadership import Groth16ProofOfLeadership


def make_block(hash: bytes, parent: bytes, slot: int) -> Block:
    return Block(
        hash=hash,
        parent_block=parent,
        slot=slot,
        block_root=b"\x00" * 32,
        proof_of_leadership=Groth16ProofOfLeadership(
            entropy_contribution=b"\x00" * 32, leader_key=b"\x00" * 32, proof=b"\x00" * 32, voucher_cm=b"\x00" * 32
        ),
    )


def snapshot(client: SqliteClient) -> Dict[bytes, tuple[int, bool]]:
    """{hash: (height, canonical)} for every stored block."""
    with client.session() as session:
        return {b.hash: (b.height, b.canonical) for b in session.exec(select(Block)).all()}


def canonical_hashes(client: SqliteClient) -> set[bytes]:
    return {h for h, (_, canonical) in snapshot(client).items() if canonical}


@pytest.fixture
def client(tmp_path):
    return SqliteClient(sqlite_db_path=f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def repo(client):
    return BlockRepository(client)


GENESIS = b"\x01"


def linear(repo: BlockRepository, n: int, *, canonical: bool = True) -> None:
    """genesis(1) <- 2 <- ... <- n, one block per slot; flagged canonical up to n by default."""
    chain = [make_block(GENESIS, parent=b"\x00", slot=0)]
    for i in range(2, n + 1):
        chain.append(make_block(bytes([i]), parent=bytes([i - 1]), slot=i))
    asyncio.run(repo.create(chain))
    if canonical:
        asyncio.run(repo.set_canonical_tip(bytes([n])))


def store(repo: BlockRepository, *blocks: Block) -> None:
    asyncio.run(repo.create(list(blocks)))


def set_tip(repo: BlockRepository, hash: bytes) -> int:
    return asyncio.run(repo.set_canonical_tip(hash))


def test_genesis_gets_height_one(client, repo):
    asyncio.run(repo.create([make_block(GENESIS, parent=b"\x00", slot=0)]))
    assert snapshot(client) == {GENESIS: (1, False)}  # nothing is canonical until the node says so


def test_linear_chain_heights(client, repo):
    linear(repo, 4)
    assert snapshot(client) == {bytes([i]): (i, True) for i in range(1, 5)}


def test_orphan_without_parent_is_dropped(client, repo):
    linear(repo, 2)
    store(repo, make_block(b"\x09", parent=b"\x08", slot=9))
    assert b"\x09" not in snapshot(client)


def test_chain_root_backfill_starts_at_height_one(client, repo):
    # A chain-walk backfill may stop before genesis; the oldest block becomes the root.
    asyncio.run(
        repo.create(
            [make_block(b"\x0a", parent=b"\x09", slot=10), make_block(b"\x0b", parent=b"\x0a", slot=11)],
            allow_chain_root=True,
        )
    )
    set_tip(repo, b"\x0b")
    assert snapshot(client) == {b"\x0a": (1, True), b"\x0b": (2, True)}


def test_duplicate_blocks_are_skipped(client, repo):
    linear(repo, 3)
    before = snapshot(client)
    store(repo, make_block(b"\x03", parent=b"\x02", slot=3), make_block(b"\x04", parent=b"\x03", slot=4))
    after = snapshot(client)
    assert {h: v for h, v in after.items() if h != b"\x04"} == before
    assert after[b"\x04"] == (4, False)


def test_set_tip_extends_chain_and_stamps_sequence(client, repo):
    linear(repo, 3)
    store(repo, make_block(b"\x04", parent=b"\x03", slot=4))
    before = asyncio.run(repo.max_canonical_seq())

    assert set_tip(repo, b"\x04") == 1
    assert canonical_hashes(client) == {bytes([i]) for i in range(1, 5)}
    assert asyncio.run(repo.max_canonical_seq()) == before + 1
    assert set_tip(repo, b"\x04") == 0  # idempotent


def test_set_tip_reorgs_above_common_ancestor_in_both_directions(client, repo):
    linear(repo, 4)  # 1 <- 2 <- 3 <- 4
    store(repo, make_block(b"\x33", parent=b"\x02", slot=5), make_block(b"\x34", parent=b"\x33", slot=6))

    # The node prefers the *shorter* branch (its fork choice is not longest-chain).
    assert set_tip(repo, b"\x34") == 2
    assert canonical_hashes(client) == {b"\x01", b"\x02", b"\x33", b"\x34"}
    assert snapshot(client)[b"\x03"] == (3, False)
    assert snapshot(client)[b"\x04"] == (4, False)

    # And back.
    assert set_tip(repo, b"\x04") == 2
    assert canonical_hashes(client) == {bytes([i]) for i in range(1, 5)}


def test_set_tip_below_current_tip_rolls_back(client, repo):
    linear(repo, 4)
    assert set_tip(repo, b"\x02") == 2  # blocks 3 and 4 un-flagged
    assert canonical_hashes(client) == {b"\x01", b"\x02"}


def test_get_latest_and_paginated_follow_canonical_chain(client, repo):
    linear(repo, 5)
    store(repo, make_block(b"\x33", parent=b"\x02", slot=9))  # sibling at height 3, never canonical

    latest = asyncio.run(repo.get_latest(3))
    assert [b.hash for b in latest] == [b"\x03", b"\x04", b"\x05"]  # oldest-first

    page, total = asyncio.run(repo.get_paginated(0, 2))
    assert total == 5  # sibling not counted
    assert [b.hash for b in page] == [b"\x05", b"\x04"]


def test_get_since_uses_canonical_stamp_not_row_id(client, repo):
    linear(repo, 2)
    store(repo, make_block(b"\x33", parent=b"\x02", slot=3))  # A  (id 3)
    store(repo, make_block(b"\x03", parent=b"\x02", slot=4))  # B  (id 4)
    store(repo, make_block(b"\x34", parent=b"\x33", slot=5))  # A' (id 5)
    set_tip(repo, b"\x34")  # node follows A's branch
    cursor = asyncio.run(repo.max_canonical_seq())
    assert asyncio.run(repo.get_since(cursor)) == []

    # Node switches to B's branch. B (id 4) is older than A' (id 5) but must still reach the stream.
    store(repo, make_block(b"\x04", parent=b"\x03", slot=6), make_block(b"\x05", parent=b"\x04", slot=7))
    set_tip(repo, b"\x05")
    delivered = asyncio.run(repo.get_since(cursor))
    assert [b.hash for b in delivered] == [b"\x03", b"\x04", b"\x05"]  # chain order
    assert all(b.canonical for b in delivered)

    # Advancing the cursor past that switch yields nothing new.
    assert asyncio.run(repo.get_since(max(b.canonical_seq for b in delivered))) == []


def test_set_tip_requires_stored_block(repo):
    with pytest.raises(ValueError):
        set_tip(repo, b"\x77")
