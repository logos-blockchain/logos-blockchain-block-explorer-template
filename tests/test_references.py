"""Searching transactions by note id or public key, via the ingestion-time reference index."""

import asyncio
from json import loads

import pytest

from api.v1.references import search_note, search_public_key
from db import Database
from models.transactions.references import references_of
from test_channels_api import block_hash, build_chain, config, extend, inscribe, make_block, make_tx, request

NOTE = b"\x10" * 32
KEY = b"\x20" * 32
OTHER = b"\x30" * 32


def transfer(inputs: list[bytes], owners: list[bytes]) -> dict:
    outputs = [{"value": 5, "public_key": owner} for owner in owners]
    return {
        "content": {"type": "LedgerTransfer", "inputs": inputs, "outputs": outputs},
        "proof": {"type": "Zk", "signature": b"\5" * 128},
    }


def pow_claim(public_key: bytes) -> dict:
    content = {"type": "ClaimPowReward", "epoch_nonce": b"\0" * 32, "block_hash": b"\0" * 32, "public_key": public_key}
    return {"content": content, "proof": {"type": "None"}}


def stored(transaction):
    transaction.id, transaction.block_id = 7, 3
    return transaction


def test_references_name_note_inputs_and_every_key_field():
    tx = stored(make_tx(1, [transfer([OTHER, NOTE], [KEY, OTHER]), inscribe(b"\xaa" * 32), config(b"\xaa" * 32)]))
    found = {(r.kind, r.key, r.op_index, r.field, r.item_index) for r in references_of(tx)}
    assert found == {
        ("note", OTHER, 0, "inputs", 0),
        ("note", NOTE, 0, "inputs", 1),
        ("public_key", KEY, 0, "outputs", 0),
        ("public_key", OTHER, 0, "outputs", 1),
        ("public_key", b"\1" * 32, 1, "signer", None),
        ("public_key", b"\3" * 32, 2, "keys", 0),
    }
    assert {(r.block_id, r.transaction_id) for r in references_of(tx)} == {(3, 7)}


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


def search(handler, db: Database, param: str, key: bytes | str, **query) -> dict:
    raw = key.hex() if isinstance(key, bytes) else key
    response = asyncio.run(handler(request(db, {param: raw}, **query)))
    return loads(response.body) | {"status_code": response.status_code}


def test_note_search_finds_spends_newest_first(db):
    build_chain(
        db,
        [
            [make_tx(1, [transfer([], [KEY])])],  # creates a note for KEY: no note id in the data
            [make_tx(2, [transfer([NOTE], [OTHER])])],
            [make_tx(3, [transfer([OTHER], [])]), make_tx(4, [transfer([OTHER, NOTE], [])])],
        ],
    )
    result = search(search_note, db, "note_id", NOTE)
    assert result["kind"] == "note" and result["key"] == NOTE.hex()
    assert [tx["hash"][-2:] for tx in result["transactions"]] == ["04", "02"]
    assert result["transactions"][0]["matches"] == [
        {"op_index": 0, "op_type": "LedgerTransfer", "field": "inputs", "item_index": 1, "role": "transfer input"}
    ]
    # The key's hex appearing elsewhere (here, as an output owner) is not a note match.
    assert search(search_note, db, "note_id", KEY)["count"] == 0


def test_public_key_search_finds_every_role_and_respects_limit(db):
    build_chain(
        db,
        [
            [make_tx(1, [transfer([], [OTHER, KEY])])],
            [make_tx(2, [pow_claim(KEY)])],
            [make_tx(3, [transfer([NOTE], [OTHER])])],  # spends a note, but names no key directly
        ],
    )
    result = search(search_public_key, db, "public_key", "0x" + KEY.hex().upper())
    assert [tx["hash"][-2:] for tx in result["transactions"]] == ["02", "01"]
    roles = [[match["role"] for match in tx["matches"]] for tx in result["transactions"]]
    assert roles == [["PoW reward claimant"], ["transfer output"]]
    assert result["transactions"][1]["matches"][0]["item_index"] == 1

    limited = search(search_public_key, db, "public_key", KEY, limit=1)
    assert (limited["count"], limited["limit"]) == (1, 1)


def test_searches_follow_the_canonical_chain(db):
    build_chain(db, [[make_tx(1, [transfer([], [KEY])])]])
    fork = make_block(block_hash(9), parent=block_hash(1), slot=5, transactions=[make_tx(2, [pow_claim(KEY)])])
    extend(db, fork, tip=False)
    assert [tx["hash"][-2:] for tx in search(search_public_key, db, "public_key", KEY)["transactions"]] == ["01"]

    extend(db, make_block(block_hash(10), parent=block_hash(9), slot=6, transactions=[]), tip=True)
    assert [tx["hash"][-2:] for tx in search(search_public_key, db, "public_key", KEY)["transactions"]] == ["02"]


def test_malformed_keys_are_400(db):
    assert search(search_public_key, db, "public_key", "abc")["status_code"] == 400
    assert search(search_note, db, "note_id", "zz" * 32)["status_code"] == 400
