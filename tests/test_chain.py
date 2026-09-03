"""Tests for height assignment and canonical-chain tracking in BlockRepository."""

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


def linear(repo: BlockRepository, n: int) -> None:
    """genesis(1) <- 2 <- ... <- n, one block per slot."""
    chain = [make_block(GENESIS, parent=b"\x00", slot=0)]
    for i in range(2, n + 1):
        chain.append(make_block(bytes([i]), parent=bytes([i - 1]), slot=i))
    asyncio.run(repo.create(chain))


def test_genesis_gets_height_one_and_is_canonical(client, repo):
    asyncio.run(repo.create([make_block(GENESIS, parent=b"\x00", slot=0)]))
    assert snapshot(client) == {GENESIS: (1, True)}


def test_linear_chain_heights_and_canonical(client, repo):
    linear(repo, 4)
    assert snapshot(client) == {bytes([i]): (i, True) for i in range(1, 5)}


def test_orphan_without_parent_is_dropped(client, repo):
    linear(repo, 2)
    asyncio.run(repo.create([make_block(b"\x09", parent=b"\x08", slot=9)]))
    assert b"\x09" not in snapshot(client)


def test_chain_root_backfill_starts_at_height_one(client, repo):
    # A chain-walk backfill may stop before genesis; the oldest block becomes the root.
    asyncio.run(
        repo.create(
            [make_block(b"\x0a", parent=b"\x09", slot=10), make_block(b"\x0b", parent=b"\x0a", slot=11)],
            allow_chain_root=True,
        )
    )
    assert snapshot(client) == {b"\x0a": (1, True), b"\x0b": (2, True)}


def test_duplicate_blocks_are_skipped(client, repo):
    linear(repo, 3)
    before = snapshot(client)
    # Same block again, alongside a genuinely new one.
    asyncio.run(repo.create([make_block(b"\x03", parent=b"\x02", slot=3), make_block(b"\x04", parent=b"\x03", slot=4)]))
    after = snapshot(client)
    assert {h: v for h, v in after.items() if h != b"\x04"} == before
    assert after[b"\x04"] == (4, True)


def test_shorter_sibling_is_not_canonical_and_ties_keep_current(client, repo):
    linear(repo, 3)  # 1 <- 2 <- 3
    asyncio.run(repo.create([make_block(b"\x33", parent=b"\x02", slot=4)]))  # sibling of 3, same height
    assert snapshot(client)[b"\x33"] == (3, False)
    assert canonical_hashes(client) == {b"\x01", b"\x02", b"\x03"}


def test_longer_sibling_reorgs_above_common_ancestor(client, repo):
    linear(repo, 4)  # 1 <- 2 <- 3 <- 4
    # Competing branch from 2: 2 <- 33 <- 34 <- 35 (height 5 beats 4)
    branch = [
        make_block(b"\x33", parent=b"\x02", slot=5),
        make_block(b"\x34", parent=b"\x33", slot=6),
        make_block(b"\x35", parent=b"\x34", slot=7),
    ]
    asyncio.run(repo.create(branch))

    assert canonical_hashes(client) == {b"\x01", b"\x02", b"\x33", b"\x34", b"\x35"}
    assert snapshot(client)[b"\x03"] == (3, False)
    assert snapshot(client)[b"\x04"] == (4, False)

    # And back again when the original branch outgrows it.
    asyncio.run(repo.create([make_block(b"\x05", parent=b"\x04", slot=8), make_block(b"\x06", parent=b"\x05", slot=9)]))
    assert canonical_hashes(client) == {bytes([i]) for i in range(1, 7)}


def test_get_latest_and_paginated_follow_canonical_chain(client, repo):
    linear(repo, 5)
    asyncio.run(repo.create([make_block(b"\x33", parent=b"\x02", slot=9)]))  # orphaned sibling at height 3

    latest = asyncio.run(repo.get_latest(3))
    assert [b.hash for b in latest] == [b"\x03", b"\x04", b"\x05"]  # oldest-first

    page, total = asyncio.run(repo.get_paginated(0, 2))
    assert total == 5  # sibling not counted
    assert [b.hash for b in page] == [b"\x05", b"\x04"]


def test_get_since_uses_canonical_stamp_not_row_id(client, repo):
    linear(repo, 2)  # 1 <- 2
    asyncio.run(repo.create([make_block(b"\x33", parent=b"\x02", slot=3)]))  # A  (id 3) height 3, canonical
    asyncio.run(repo.create([make_block(b"\x03", parent=b"\x02", slot=4)]))  # B  (id 4) height 3, loses the tie
    asyncio.run(repo.create([make_block(b"\x34", parent=b"\x33", slot=5)]))  # A' (id 5) height 4, canonical
    cursor = asyncio.run(repo.max_canonical_seq())
    assert asyncio.run(repo.get_since(cursor)) == []

    # B's branch grows to height 5 and wins. B (id 4) is older than A' (id 5)
    # but must still reach the stream.
    asyncio.run(repo.create([make_block(b"\x04", parent=b"\x03", slot=6), make_block(b"\x05", parent=b"\x04", slot=7)]))
    delivered = asyncio.run(repo.get_since(cursor))
    assert [b.hash for b in delivered] == [b"\x03", b"\x04", b"\x05"]  # chain order
    assert all(b.canonical for b in delivered)

    # Advancing the cursor past that switch yields nothing new.
    assert asyncio.run(repo.get_since(max(b.canonical_seq for b in delivered))) == []
