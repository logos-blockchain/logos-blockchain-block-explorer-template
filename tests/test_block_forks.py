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
