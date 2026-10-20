"""Copied block columns, chain transaction totals and channel totals stay exact through reorgs.

Each is checked against a brute-force recomputation from `block.canonical` after
every tip switch on a randomly grown block tree.
"""

import random

import pytest

from db import Database
from models.transactions.transaction import Transaction
from test_channels_api import inscribe, make_block, make_tx, transfer

CHANNELS = [bytes([c]) * 32 for c in (0xA1, 0xA2, 0xA3)]


def random_transactions(rng: random.Random, seed: int) -> list[Transaction]:
    transactions = []
    for i in range(rng.choice([0, 0, 1, 2, 3])):
        ops = [inscribe(rng.choice(CHANNELS)) if rng.random() < 0.5 else transfer() for _ in range(rng.randint(1, 3))]
        transactions.append(make_tx(seed * 10 + i, ops))
    return transactions


def assert_derived_state_matches(db: Database) -> None:
    conn = db.conn
    for table, copied in (("tx", "height"), ("tx_reference", "height"), ("channel_operation", "height, canonical")):
        mismatched = conn.execute(
            f"SELECT COUNT(*) FROM {table} c JOIN block b ON b.id = c.block_id"
            f" WHERE ({', '.join('c.' + col for col in copied.split(', '))})"
            f" != ({', '.join('b.' + col for col in copied.split(', '))})"
        ).fetchone()[0]
        assert mismatched == 0, table

    expected_channels = conn.execute(
        "SELECT c.channel_id, COUNT(*), MAX(b.height) FROM channel_operation c JOIN block b ON b.id = c.block_id"
        " WHERE b.canonical = 1 GROUP BY c.channel_id ORDER BY c.channel_id"
    ).fetchall()
    assert conn.execute("SELECT channel_id, op_count, last_height FROM channel ORDER BY channel_id").fetchall() == (
        expected_channels
    )

    expected_txs = [
        row[0]
        for row in conn.execute(
            "SELECT t.hash FROM tx t JOIN block b ON b.id = t.block_id WHERE b.canonical = 1"
            " ORDER BY b.height DESC, t.id DESC"
        )
    ]
    for page_size in (1, 3, 7):
        pages, total = [], None
        for page in range(len(expected_txs) // page_size + 2):
            pairs, total = db.paginated_transactions(page, page_size)
            pages += [transaction.hash for transaction, _ in pairs]
        assert (pages, total) == (expected_txs, len(expected_txs))

    expected_blocks = [row[0] for row in conn.execute("SELECT hash FROM block WHERE canonical = 1 ORDER BY height DESC")]
    pages = []
    for page in range(len(expected_blocks) // 4 + 2):
        blocks, total = db.paginated_blocks(page, 4)
        pages += [block.hash for block in blocks]
        assert total == len(expected_blocks)
    assert pages == expected_blocks


@pytest.mark.parametrize("seed", range(5))
def test_derived_state_survives_random_reorgs(tmp_path, seed):
    rng = random.Random(seed)
    db = Database(str(tmp_path / "test.db"))
    genesis = make_block(b"\x00" * 31 + b"\x01", parent=b"\x00" * 32, slot=0, transactions=random_transactions(rng, 1))
    db.store_blocks([genesis])
    db.set_canonical_tip(genesis.hash)
    hashes = [genesis.hash]

    for n in range(2, 60):
        # Grow mostly from recent blocks so branches of several blocks form.
        parent = rng.choice(hashes[-6:])
        block = make_block(n.to_bytes(32, "big"), parent=parent, slot=n, transactions=random_transactions(rng, n))
        db.store_blocks([block])
        hashes.append(block.hash)
        if rng.random() < 0.6:
            db.set_canonical_tip(rng.choice(hashes[-8:]))  # forward, sideways (reorg) or back (rollback)
            assert_derived_state_matches(db)
