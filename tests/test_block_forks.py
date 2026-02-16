"""Tests for fork tracking in BlockRepository."""

import asyncio
import os
from typing import Dict

import pytest
from sqlmodel import select

from db.blocks import BlockRepository
from db.clients.sqlite import SqliteClient
from models.block import Block
from models.header.proof_of_leadership import Groth16ProofOfLeadership


def make_block(hash: bytes, parent: bytes, slot: int) -> Block:
    """Create a minimal Block for testing."""
    return Block(
        hash=hash,
        parent_block=parent,
        slot=slot,
        block_root=b"\x00" * 32,
        proof_of_leadership=Groth16ProofOfLeadership(
            entropy_contribution=b"\x00" * 32,
            leader_key=b"\x00" * 32,
            proof=b"\x00" * 32,
            voucher_cm=b"\x00" * 32,
        ),
    )


def get_forks(client: SqliteClient) -> Dict[bytes, int]:
    """Return a {hash: fork} mapping for all blocks in the DB."""
    with client.session() as session:
        blocks = session.exec(select(Block)).all()
        return {b.hash: b.fork for b in blocks}


@pytest.fixture
def client(tmp_path):
    db_path = f"sqlite:///{tmp_path / 'test.db'}"
    return SqliteClient(sqlite_db_path=db_path)


@pytest.fixture
def repo(client):
    return BlockRepository(client)


def test_genesis_block_gets_fork_zero(client, repo):
    """A genesis block (slot 0) should get fork 0."""
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    forks = get_forks(client)
    assert forks[b"\x01"] == 0


def test_linear_chain_inherits_fork(client, repo):
    """
    A linear chain with no forks should all share the same fork number.

    genesis -> A -> B -> C   (all fork 0)
    """
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    asyncio.run(repo.create(a))

    b = make_block(b"\x03", parent=b"\x02", slot=2)
    asyncio.run(repo.create(b))

    c = make_block(b"\x04", parent=b"\x03", slot=3)
    asyncio.run(repo.create(c))

    forks = get_forks(client)
    assert forks[b"\x01"] == 0
    assert forks[b"\x02"] == 0
    assert forks[b"\x03"] == 0
    assert forks[b"\x04"] == 0


def test_fork_on_second_child(client, repo):
    """
    When two blocks share the same parent, the second one creates a new fork.

    genesis -> A   (fork 0, first child)
           \\-> B   (fork 1, second child — triggers new fork)
    """
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    asyncio.run(repo.create(a))

    # B has the same parent as A
    b = make_block(b"\x03", parent=b"\x01", slot=1)
    asyncio.run(repo.create(b))

    forks = get_forks(client)
    assert forks[b"\x01"] == 0
    assert forks[b"\x02"] == 0
    assert forks[b"\x03"] == 1  # new fork


def test_fork_descendants_inherit(client, repo):
    """
    Descendants of a forked block should inherit the fork number.

    genesis -> A -> C   (all fork 0)
           \\-> B -> D   (B is fork 1, D inherits fork 1)
    """
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    asyncio.run(repo.create(a))

    b = make_block(b"\x03", parent=b"\x01", slot=1)
    asyncio.run(repo.create(b))

    # C extends A (fork 0)
    c = make_block(b"\x04", parent=b"\x02", slot=2)
    asyncio.run(repo.create(c))

    # D extends B (fork 1)
    d = make_block(b"\x05", parent=b"\x03", slot=2)
    asyncio.run(repo.create(d))

    forks = get_forks(client)
    assert forks[b"\x04"] == 0  # inherits from A
    assert forks[b"\x05"] == 1  # inherits from B


def test_multiple_forks_from_same_parent(client, repo):
    """
    Three children of the same parent: first inherits, others get new forks.

    genesis -> A   (fork 0)
           \\-> B   (fork 1)
           \\-> C   (fork 2)
    """
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    asyncio.run(repo.create(a))

    b = make_block(b"\x03", parent=b"\x01", slot=1)
    asyncio.run(repo.create(b))

    c = make_block(b"\x04", parent=b"\x01", slot=1)
    asyncio.run(repo.create(c))

    forks = get_forks(client)
    assert forks[b"\x02"] == 0
    assert forks[b"\x03"] == 1
    assert forks[b"\x04"] == 2


def test_fork_in_same_batch(client, repo):
    """
    Two siblings submitted in the same batch should get different forks.

    genesis -> A   (fork 0)
           \\-> B   (fork 1)
    """
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    b = make_block(b"\x03", parent=b"\x01", slot=1)
    asyncio.run(repo.create(a, b))

    forks = get_forks(client)
    assert forks[b"\x02"] == 0  # first child inherits
    assert forks[b"\x03"] == 1  # second child gets new fork


def test_chain_in_single_batch(client, repo):
    """
    A full chain submitted as one batch: genesis -> A -> B, all fork 0.
    """
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    a = make_block(b"\x02", parent=b"\x01", slot=1)
    b = make_block(b"\x03", parent=b"\x02", slot=2)
    asyncio.run(repo.create(genesis, a, b))

    forks = get_forks(client)
    assert forks[b"\x01"] == 0
    assert forks[b"\x02"] == 0
    assert forks[b"\x03"] == 0


def test_fork_numbering_is_global(client, repo):
    """
    Fork numbers are global, not per-parent. A fork at one point in the tree
    doesn't reset the counter.

    genesis -> A -> C   (fork 0)
           \\-> B       (fork 1)
                  C \\-> D   (fork 0, inherits from C)
                    \\-> E   (fork 2, not fork 1 — counter is global)
    """
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    asyncio.run(repo.create(a))

    # Fork at genesis
    b = make_block(b"\x03", parent=b"\x01", slot=1)
    asyncio.run(repo.create(b))  # fork 1

    c = make_block(b"\x04", parent=b"\x02", slot=2)
    asyncio.run(repo.create(c))

    # First child of C
    d = make_block(b"\x05", parent=b"\x04", slot=3)
    asyncio.run(repo.create(d))

    # Second child of C — should be fork 2, not 1
    e = make_block(b"\x06", parent=b"\x04", slot=3)
    asyncio.run(repo.create(e))

    forks = get_forks(client)
    assert forks[b"\x03"] == 1  # first fork
    assert forks[b"\x05"] == 0  # inherits from C (fork 0)
    assert forks[b"\x06"] == 2  # new fork, global counter


def test_batch_with_fork_and_chain(client, repo):
    """
    A batch containing both a fork point and a chain extending from it.

    genesis is already in DB. Batch contains:
      A (parent=genesis), B (parent=genesis), C (parent=A)

    Expected: A=fork 0, B=fork 1, C=fork 0 (inherits from A)
    """
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    b = make_block(b"\x03", parent=b"\x01", slot=1)
    c = make_block(b"\x04", parent=b"\x02", slot=2)
    asyncio.run(repo.create(a, b, c))

    forks = get_forks(client)
    assert forks[b"\x02"] == 0  # A inherits from genesis
    assert forks[b"\x03"] == 1  # B forks
    assert forks[b"\x04"] == 0  # C inherits from A


# --- Fork choice tests ---


def test_fork_choice_empty_db(client, repo):
    """Fork choice returns Empty when no blocks exist."""
    from rusty_results import Empty
    result = asyncio.run(repo.get_fork_choice())
    assert isinstance(result, Empty)


def test_fork_choice_single_chain(client, repo):
    """Fork choice returns fork 0 for a single linear chain."""
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    a = make_block(b"\x02", parent=b"\x01", slot=1)
    asyncio.run(repo.create(genesis, a))

    result = asyncio.run(repo.get_fork_choice())
    assert result.unwrap() == 0


def test_fork_choice_returns_longest_fork(client, repo):
    """
    Fork choice returns the fork with the highest block.

    genesis -> A -> C   (fork 0, height 2)
           \\-> B       (fork 1, height 1)

    Fork 0 is longer, so fork choice should return 0.
    """
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    asyncio.run(repo.create(a))

    b = make_block(b"\x03", parent=b"\x01", slot=1)
    asyncio.run(repo.create(b))

    c = make_block(b"\x04", parent=b"\x02", slot=2)
    asyncio.run(repo.create(c))

    result = asyncio.run(repo.get_fork_choice())
    assert result.unwrap() == 0


def test_fork_choice_switches_on_overtake(client, repo):
    """
    Fork choice switches when the alternative fork grows longer.

    genesis -> A       (fork 0, height 1)
           \\-> B -> C  (fork 1, height 2)

    Fork 1 is longer, so fork choice should return 1.
    """
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    asyncio.run(repo.create(a))

    b = make_block(b"\x03", parent=b"\x01", slot=1)
    asyncio.run(repo.create(b))

    # Fork 0 has height 1 (block A). Now extend fork 1 past it.
    c = make_block(b"\x04", parent=b"\x03", slot=2)
    asyncio.run(repo.create(c))

    result = asyncio.run(repo.get_fork_choice())
    assert result.unwrap() == 1


# --- Fork-filtered query tests ---


def test_get_latest_filters_by_fork(client, repo):
    """get_latest with fork filter only returns blocks from that fork."""
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    asyncio.run(repo.create(a))

    b = make_block(b"\x03", parent=b"\x01", slot=1)
    asyncio.run(repo.create(b))

    # Fork 0: genesis, A.  Fork 1: B (but B also shares genesis at fork 0... no, genesis is fork 0)
    # Actually: genesis=fork0, A=fork0, B=fork1
    fork0_blocks = asyncio.run(repo.get_latest(10, fork=0))
    fork1_blocks = asyncio.run(repo.get_latest(10, fork=1))

    fork0_hashes = {b.hash for b in fork0_blocks}
    fork1_hashes = {b.hash for b in fork1_blocks}

    assert b"\x01" in fork0_hashes  # genesis
    assert b"\x02" in fork0_hashes  # A
    assert b"\x03" not in fork0_hashes

    assert b"\x03" in fork1_hashes  # B
    assert b"\x02" not in fork1_hashes


def test_get_paginated_filters_by_fork(client, repo):
    """get_paginated with fork filter only returns blocks from that fork."""
    genesis = make_block(b"\x01", parent=b"\x00", slot=0)
    asyncio.run(repo.create(genesis))

    a = make_block(b"\x02", parent=b"\x01", slot=1)
    asyncio.run(repo.create(a))

    b = make_block(b"\x03", parent=b"\x01", slot=1)
    asyncio.run(repo.create(b))

    blocks_f0, count_f0 = asyncio.run(repo.get_paginated(0, 10, fork=0))
    blocks_f1, count_f1 = asyncio.run(repo.get_paginated(0, 10, fork=1))

    assert count_f0 == 2  # genesis + A
    assert count_f1 == 1  # B only
    assert {b.hash for b in blocks_f0} == {b"\x01", b"\x02"}
    assert {b.hash for b in blocks_f1} == {b"\x03"}
