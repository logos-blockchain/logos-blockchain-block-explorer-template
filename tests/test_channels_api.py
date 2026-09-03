"""Tests for the ingestion-time channel index behind /api/v1/channels/*."""

import asyncio
from json import loads
from types import SimpleNamespace

import pytest
from sqlmodel import select

from api.v1.channels import get_channel, list_channels
from db.blocks import BlockRepository
from db.channels import ChannelOperationRepository
from db.clients.sqlite import SqliteClient
from models.block import Block
from models.channel_operation import ChannelOperation
from models.header.proof_of_leadership import Groth16ProofOfLeadership
from models.transactions.transaction import Transaction

CH_A = b"\xaa" * 32
CH_B = b"\xbb" * 32
CH_C = b"\xcc" * 32


def inscribe(channel: bytes, text: bytes = b"hello") -> dict:
    return {
        "content": {
            "type": "ChannelInscribe",
            "channel_id": channel,
            "inscription": text,
            "parent": b"\0" * 32,
            "signer": b"\1" * 32,
        },
        "proof": {"type": "Ed25519", "signature": b"\2" * 64},
    }


def config(channel: bytes) -> dict:
    return {
        "content": {
            "type": "ChannelConfig",
            "channel": channel,
            "keys": [b"\3" * 32],
            "posting_timeframe": 1,
            "posting_timeout": 1,
            "configuration_threshold": 1,
            "transfer_threshold": 1,
        },
        "proof": {"type": "ChannelMultiSig", "signatures": []},
    }


def transfer() -> dict:
    return {
        "content": {"type": "LedgerTransfer", "inputs": [b"\4" * 32], "outputs": []},
        "proof": {"type": "Zk", "signature": b"\5" * 128},
    }


def make_tx(seed: int, operations: list[dict]) -> Transaction:
    return Transaction.model_validate(
        {"hash": seed.to_bytes(32, "big"), "operations": operations, "execution_gas_price": 0, "storage_gas_price": 0}
    )


def make_block(hash: bytes, parent: bytes, slot: int, transactions: list[Transaction]) -> Block:
    return Block(
        hash=hash,
        parent_block=parent,
        slot=slot,
        block_root=b"\x00" * 32,
        proof_of_leadership=Groth16ProofOfLeadership(
            entropy_contribution=b"\x00" * 32, leader_key=b"\x00" * 32, proof=b"\x00" * 32, voucher_cm=b"\x00" * 32
        ),
    ).with_transactions(transactions)


def block_hash(n: int) -> bytes:
    return n.to_bytes(32, "little")


@pytest.fixture
def client(tmp_path):
    return SqliteClient(sqlite_db_path=f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def blocks(client):
    return BlockRepository(client)


@pytest.fixture
def channels(client):
    return ChannelOperationRepository(client)


@pytest.fixture
def request_for(channels):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(channel_repository=channels)))


def build_chain(blocks: BlockRepository, txs_per_height: list[list[Transaction]]) -> None:
    """Linear chain: block at height h+1 (slot h*10) holds txs_per_height[h]. Genesis is slot 0."""
    chain = [make_block(block_hash(1), parent=b"\0" * 32, slot=0, transactions=[])]
    for i, txs in enumerate(txs_per_height, start=2):
        chain.append(make_block(block_hash(i), parent=block_hash(i - 1), slot=(i - 1) * 10, transactions=txs))
    asyncio.run(blocks.create(chain, allow_chain_root=True))


def test_channel_ops_are_indexed_at_ingestion(client, blocks):
    build_chain(blocks, [[make_tx(1, [inscribe(CH_A), transfer(), config(CH_B)])], [make_tx(2, [inscribe(CH_A)])]])

    with client.session() as session:
        rows = session.exec(select(ChannelOperation).order_by(ChannelOperation.id)).all()

    assert [(r.channel_id, r.op_type, r.op_index) for r in rows] == [
        (CH_A, "ChannelInscribe", 0),
        (CH_B, "ChannelConfig", 2),  # non-channel op at index 1 is skipped, index preserved
        (CH_A, "ChannelInscribe", 0),
    ]
    assert all(r.block_id is not None and r.transaction_id is not None for r in rows)


def test_list_counts_whole_history_and_keeps_old_channels(blocks, request_for):
    # CH_A is active early then goes quiet; CH_B is only recent. A window-based
    # aggregation would rank B first (or drop A entirely) once enough non-channel
    # traffic arrives. The index must report exact totals regardless.
    early = [[make_tx(i, [inscribe(CH_A)])] for i in range(1, 6)]  # 5 ops on A
    quiet = [[make_tx(100 + i, [transfer()])] for i in range(300)]  # lots of unrelated traffic
    recent = [[make_tx(500 + i, [inscribe(CH_B)])] for i in range(2)]  # 2 ops on B
    build_chain(blocks, early + quiet + recent)

    payload = loads(asyncio.run(list_channels(request_for, limit=8, ops_limit=3)).body)

    by_id = {ch["channel_id"]: ch for ch in payload["channels"]}
    assert [ch["channel_id"] for ch in payload["channels"]] == [CH_A.hex(), CH_B.hex()]
    assert by_id[CH_A.hex()]["op_count"] == 5
    assert by_id[CH_B.hex()]["op_count"] == 2
    # Newest ops first, capped at ops_limit.
    assert [op["height"] for op in by_id[CH_A.hex()]["operations"]] == [6, 5, 4]
    assert by_id[CH_A.hex()]["last_height"] == 6
    assert by_id[CH_A.hex()]["last_slot"] == 50
    assert by_id[CH_A.hex()]["operations"][0]["content"]["type"] == "ChannelInscribe"


def test_list_respects_limit_and_ties_break_by_recency(blocks, request_for):
    build_chain(
        blocks, [[make_tx(1, [inscribe(CH_A)])], [make_tx(2, [inscribe(CH_B)])], [make_tx(3, [inscribe(CH_C)])]]
    )

    payload = loads(asyncio.run(list_channels(request_for, limit=2, ops_limit=25)).body)

    assert [ch["channel_id"] for ch in payload["channels"]] == [CH_C.hex(), CH_B.hex()]


def test_get_channel_paginates_with_stable_indices(blocks, request_for):
    build_chain(blocks, [[make_tx(i, [inscribe(CH_A, bytes([i]))])] for i in range(1, 6)])

    page1 = loads(asyncio.run(get_channel(request_for, CH_A.hex(), page=1, page_size=2)).body)

    assert page1["op_count"] == 5
    assert page1["page"] == 1
    assert [op["index"] for op in page1["operations"]] == [2, 3]
    assert [op["height"] for op in page1["operations"]] == [4, 5]
    assert [op["content"]["inscription"] for op in page1["operations"]] == ["03", "04"]

    last = loads(asyncio.run(get_channel(request_for, CH_A.hex(), page=2, page_size=2)).body)
    assert [op["index"] for op in last["operations"]] == [4]


def test_get_channel_orders_ops_within_a_block(blocks, request_for):
    # Two txs in one block, several channel ops each: order is tx order, then op position.
    build_chain(
        blocks,
        [[make_tx(1, [inscribe(CH_A, b"a0"), transfer(), inscribe(CH_A, b"a2")]), make_tx(2, [inscribe(CH_A, b"b0")])]],
    )

    payload = loads(asyncio.run(get_channel(request_for, CH_A.hex(), page=0, page_size=25)).body)

    assert [bytes.fromhex(op["content"]["inscription"]) for op in payload["operations"]] == [b"a0", b"a2", b"b0"]


def test_get_channel_accepts_uppercase_and_0x_prefix(blocks, request_for):
    build_chain(blocks, [[make_tx(1, [inscribe(CH_A)])]])

    payload = loads(asyncio.run(get_channel(request_for, "0x" + CH_A.hex().upper(), page=0, page_size=25)).body)

    assert payload["channel_id"] == CH_A.hex()
    assert payload["op_count"] == 1


def test_get_channel_rejects_malformed_id(request_for):
    response = asyncio.run(get_channel(request_for, "not-hex", page=0, page_size=25))
    assert response.status_code == 400


def test_channels_follow_the_canonical_chain(blocks, request_for):
    build_chain(blocks, [[make_tx(1, [inscribe(CH_A)])]])  # genesis(1) <- block 2 (height 2)
    asyncio.run(
        blocks.create(
            [make_block(block_hash(3), parent=block_hash(2), slot=20, transactions=[make_tx(2, [inscribe(CH_A)])])]
        )
    )
    # A same-height sibling with a CH_B op is not canonical, so it does not count.
    asyncio.run(
        blocks.create(
            [make_block(block_hash(4), parent=block_hash(2), slot=21, transactions=[make_tx(3, [inscribe(CH_B)])])]
        )
    )
    payload = loads(asyncio.run(list_channels(request_for, limit=8, ops_limit=25)).body)
    assert {ch["channel_id"]: ch["op_count"] for ch in payload["channels"]} == {CH_A.hex(): 2}

    # Extending the sibling branch makes it the longest chain: block 3's op drops out, CH_B's ops appear.
    asyncio.run(
        blocks.create(
            [make_block(block_hash(5), parent=block_hash(4), slot=22, transactions=[make_tx(4, [inscribe(CH_B)])])]
        )
    )
    payload = loads(asyncio.run(list_channels(request_for, limit=8, ops_limit=25)).body)
    assert {ch["channel_id"]: ch["op_count"] for ch in payload["channels"]} == {CH_B.hex(): 2, CH_A.hex(): 1}
