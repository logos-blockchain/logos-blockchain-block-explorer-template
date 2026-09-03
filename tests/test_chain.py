"""Tests for height assignment and canonical-chain tracking in the database.

Blocks are stored non-canonical; `set_canonical_tip` applies the node's fork
choice, which is not plain longest-chain.
"""

from typing import Dict

import pytest

from db import Database
from models.block import Block
from models.header.proof_of_leadership import Groth16ProofOfLeadership
from models.transactions.transaction import Transaction


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


def snapshot(db: Database) -> Dict[bytes, tuple[int, bool]]:
    """{hash: (height, canonical)} for every stored block."""
    rows = db.conn.execute("SELECT hash, height, canonical FROM block")
    return {hash_: (height, bool(canonical)) for hash_, height, canonical in rows}


def canonical_hashes(db: Database) -> set[bytes]:
    return {h for h, (_, canonical) in snapshot(db).items() if canonical}


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


GENESIS = b"\x01"


def linear(db: Database, n: int, *, canonical: bool = True) -> None:
    """genesis(1) <- 2 <- ... <- n, one block per slot; flagged canonical up to n by default."""
    chain = [make_block(GENESIS, parent=b"\x00", slot=0)]
    for i in range(2, n + 1):
        chain.append(make_block(bytes([i]), parent=bytes([i - 1]), slot=i))
    db.store_blocks(chain)
    if canonical:
        db.set_canonical_tip(bytes([n]))


def test_genesis_gets_height_one(db):
    db.store_blocks([make_block(GENESIS, parent=b"\x00", slot=0)])
    assert snapshot(db) == {GENESIS: (1, False)}  # nothing is canonical until the node says so


def test_linear_chain_heights(db):
    linear(db, 4)
    assert snapshot(db) == {bytes([i]): (i, True) for i in range(1, 5)}


def test_store_writes_ids_and_heights_back(db):
    genesis, child = make_block(GENESIS, parent=b"\x00", slot=0), make_block(b"\x02", parent=GENESIS, slot=1)
    db.store_blocks([child, genesis])  # order inside a batch does not matter
    assert (genesis.id, genesis.height) == (1, 1)
    assert (child.id, child.height) == (2, 2)


def test_orphan_without_parent_is_dropped(db):
    linear(db, 2)
    db.store_blocks([make_block(b"\x09", parent=b"\x08", slot=9)])
    assert b"\x09" not in snapshot(db)


def test_chain_root_backfill_starts_at_height_one(db):
    # A chain-walk backfill may stop before genesis; the oldest block becomes the root.
    db.store_blocks(
        [make_block(b"\x0a", parent=b"\x09", slot=10), make_block(b"\x0b", parent=b"\x0a", slot=11)],
        allow_chain_root=True,
    )
    db.set_canonical_tip(b"\x0b")
    assert snapshot(db) == {b"\x0a": (1, True), b"\x0b": (2, True)}


def test_duplicate_blocks_are_skipped(db):
    linear(db, 3)
    before = snapshot(db)
    db.store_blocks([make_block(b"\x03", parent=b"\x02", slot=3), make_block(b"\x04", parent=b"\x03", slot=4)])
    after = snapshot(db)
    assert {h: v for h, v in after.items() if h != b"\x04"} == before
    assert after[b"\x04"] == (4, False)


def test_set_tip_extends_chain_and_stamps_sequence(db):
    linear(db, 3)
    db.store_blocks([make_block(b"\x04", parent=b"\x03", slot=4)])
    before = db.max_canonical_seq()

    assert db.set_canonical_tip(b"\x04") == 1
    assert canonical_hashes(db) == {bytes([i]) for i in range(1, 5)}
    assert db.max_canonical_seq() == before + 1
    assert db.set_canonical_tip(b"\x04") == 0  # idempotent


def test_set_tip_reorgs_above_common_ancestor_in_both_directions(db):
    linear(db, 4)  # 1 <- 2 <- 3 <- 4
    db.store_blocks([make_block(b"\x33", parent=b"\x02", slot=5), make_block(b"\x34", parent=b"\x33", slot=6)])

    # The node prefers the *shorter* branch (its fork choice is not longest-chain).
    assert db.set_canonical_tip(b"\x34") == 2
    assert canonical_hashes(db) == {b"\x01", b"\x02", b"\x33", b"\x34"}
    assert snapshot(db)[b"\x03"] == (3, False)
    assert snapshot(db)[b"\x04"] == (4, False)

    # And back.
    assert db.set_canonical_tip(b"\x04") == 2
    assert canonical_hashes(db) == {bytes([i]) for i in range(1, 5)}


def test_set_tip_below_current_tip_rolls_back(db):
    linear(db, 4)
    assert db.set_canonical_tip(b"\x02") == 2  # blocks 3 and 4 un-flagged
    assert canonical_hashes(db) == {b"\x01", b"\x02"}


def test_get_latest_and_paginated_follow_canonical_chain(db):
    linear(db, 5)
    db.store_blocks([make_block(b"\x33", parent=b"\x02", slot=9)])  # sibling at height 3, never canonical

    latest = db.latest_blocks(3)
    assert [b.hash for b in latest] == [b"\x03", b"\x04", b"\x05"]  # oldest-first

    page, total = db.paginated_blocks(0, 2)
    assert total == 5  # sibling not counted
    assert [b.hash for b in page] == [b"\x05", b"\x04"]


def test_get_since_uses_canonical_stamp_not_row_id(db):
    linear(db, 2)
    db.store_blocks([make_block(b"\x33", parent=b"\x02", slot=3)])  # A  (id 3)
    db.store_blocks([make_block(b"\x03", parent=b"\x02", slot=4)])  # B  (id 4)
    db.store_blocks([make_block(b"\x34", parent=b"\x33", slot=5)])  # A' (id 5)
    db.set_canonical_tip(b"\x34")  # node follows A's branch
    cursor = db.max_canonical_seq()
    assert db.blocks_since(cursor) == []

    # Node switches to B's branch. B (id 4) is older than A' (id 5) but must still reach the stream.
    db.store_blocks([make_block(b"\x04", parent=b"\x03", slot=6), make_block(b"\x05", parent=b"\x04", slot=7)])
    db.set_canonical_tip(b"\x05")
    delivered = db.blocks_since(cursor)
    assert [b.hash for b in delivered] == [b"\x03", b"\x04", b"\x05"]  # chain order
    assert all(b.canonical for b in delivered)

    # Advancing the cursor past that switch yields nothing new.
    assert db.blocks_since(max(b.canonical_seq for b in delivered)) == []


def test_set_tip_requires_stored_block(db):
    with pytest.raises(ValueError):
        db.set_canonical_tip(b"\x77")


def test_block_round_trips_with_its_transactions(db):
    block = make_block(GENESIS, parent=b"\x00", slot=0)
    content = {"type": "LedgerTransfer", "inputs": [b"\x0b" * 32], "outputs": []}
    transfer = {"content": content, "proof": {"type": "None"}}
    block.transactions = [Transaction.model_validate({"hash": b"\x0a" * 32, "operations": [transfer]})]
    db.store_blocks([block])

    stored = db.block_by_hash(GENESIS)
    assert stored.proof_of_leadership == block.proof_of_leadership
    assert [t.hash for t in stored.transactions] == [b"\x0a" * 32]
    assert stored.transactions[0].operations == block.transactions[0].operations
    assert stored.transactions[0].block_id == stored.id

    transaction, in_block = db.transaction_by_hash(b"\x0a" * 32)
    assert (transaction.id, in_block.hash) == (stored.transactions[0].id, GENESIS)
