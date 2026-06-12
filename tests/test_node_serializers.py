"""Tests for node API serializers against the current (0.1.3-rc) wire format.

The fixtures are real data: block_new_format.json is a block captured from a
node, and ops_samples_testnet.json holds per-opcode op/proof samples harvested
from the chain.
"""

import json
from pathlib import Path

import pytest

from node.api.http import normalize_info_payload
from node.api.serializers.block import BlockSerializer
from node.api.serializers.fields import bytes_from_hex_or_intarray
from node.api.serializers.info import InfoSerializer
from node.api.serializers.operation import ChannelSetKeysOpSerializer, UnknownOpSerializer
from node.api.serializers.proof import Ed25519SignatureSerializer

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def block() -> dict:
    return json.loads((FIXTURES / "block_new_format.json").read_text())


class TestInfoNormalization:
    def test_nested_format(self):
        payload = {
            "cryptarchia_info": {"lib": "aa", "lib_slot": 9, "tip": "bb", "slot": 10, "height": 3},
            "mode": {"Started": "Online"},
        }
        info = InfoSerializer.model_validate(normalize_info_payload(payload))
        assert info.mode == "Online"
        assert info.height == 3
        assert info.tip == "bb"

    def test_flat_format_passes_through(self):
        payload = {"lib": "aa", "tip": "bb", "slot": 1, "height": 2, "mode": "Online"}
        info = InfoSerializer.model_validate(normalize_info_payload(payload))
        assert info.mode == "Online"
        assert info.height == 2


class TestHexOrIntArrayField:
    def test_accepts_hex_string(self):
        assert bytes_from_hex_or_intarray("68656c6c6f") == b"hello"

    def test_accepts_int_array(self):
        assert bytes_from_hex_or_intarray([104, 101, 108, 108, 111]) == b"hello"

    def test_rejects_other_types(self):
        with pytest.raises(ValueError):
            bytes_from_hex_or_intarray(42)


class TestBlockParsing:
    def test_parses_real_block(self, block):
        parsed = BlockSerializer.model_validate(block)
        assert parsed.header.slot == block["header"]["slot"]
        assert len(parsed.transactions) == len(block["transactions"])

    def test_tx_hash_comes_from_node(self, block):
        parsed = BlockSerializer.model_validate(block)
        tx = parsed.transactions[0].into_transaction()
        expected = bytes.fromhex(block["transactions"][0]["mantle_tx"]["hash"])
        assert tx.hash == expected

    def test_inscription_decodes_from_hex(self, block):
        parsed = BlockSerializer.model_validate(block)
        op = parsed.transactions[0].transaction.ops[0]
        raw_hex = block["transactions"][0]["mantle_tx"]["ops"][0]["payload"]["inscription"]
        assert op.inscription == bytes.fromhex(raw_hex)
        # Sequencer inscriptions reference LEZ program accounts.
        assert b"/LEZ/" in op.inscription

    def test_ed25519_proof_from_hex(self, block):
        parsed = BlockSerializer.model_validate(block)
        proof = parsed.transactions[0].operations_proofs[0]
        assert isinstance(proof, Ed25519SignatureSerializer)
        assert len(proof.root) == 64

    def test_into_block_roundtrip(self, block):
        parsed = BlockSerializer.model_validate(block).into_block()
        assert parsed.hash == bytes.fromhex(block["header"]["id"])
        assert parsed.transactions[0].operations[0].content.type == "ChannelInscribe"

    def test_missing_gas_prices_default_to_zero(self, block):
        parsed = BlockSerializer.model_validate(block)
        tx = parsed.transactions[0].into_transaction()
        assert tx.execution_gas_price == 0
        assert tx.storage_gas_price == 0

    def test_hash_fallback_when_node_omits_it(self, block):
        del block["transactions"][0]["mantle_tx"]["hash"]
        parsed = BlockSerializer.model_validate(block)
        tx = parsed.transactions[0].into_transaction()
        assert len(tx.hash) == 32  # deterministic local fallback


class TestUnknownOps:
    def test_unknown_opcode_is_preserved_not_fatal(self, block):
        block["transactions"][0]["mantle_tx"]["ops"][0]["opcode"] = 99
        parsed = BlockSerializer.model_validate(block)
        op = parsed.transactions[0].transaction.ops[0]
        assert isinstance(op, UnknownOpSerializer)
        assert op.opcode == 99
        content = parsed.transactions[0].into_transaction().operations[0].content
        assert content.type == "UnknownOp"
        assert content.opcode == 99
        assert content.raw_payload is not None  # raw payload preserved verbatim

    def test_unknown_op_with_noproof_is_preserved_not_fatal(self, block):
        # e.g. a LeaderClaim carries no proof; neither the op nor the
        # "NoProof" unit variant should break ingestion.
        tx = block["transactions"][0]
        tx["mantle_tx"]["ops"][0] = {"opcode": 48, "payload": {"rewards_root": "aa" * 32}}
        tx["ops_proofs"][0] = "NoProof"
        parsed = BlockSerializer.model_validate(block)
        operation = parsed.transactions[0].into_transaction().operations[0]
        assert operation.content.type == "UnknownOp"
        assert operation.content.opcode == 48
        assert operation.proof.type == "Unknown"
        assert operation.proof.raw == "NoProof"


class TestChannelSetKeysOp:
    @pytest.fixture
    def setkeys_sample(self) -> dict:
        """Real opcode 16 op + proof captured from the chain."""
        samples = json.loads((FIXTURES / "ops_samples_testnet.json").read_text())
        return samples["16"]

    def test_real_sample_parses(self, block, setkeys_sample):
        tx = block["transactions"][0]
        tx["mantle_tx"]["ops"] = [{"opcode": 16, "payload": setkeys_sample["payload"]}]
        tx["ops_proofs"] = [setkeys_sample["proof"]]
        parsed = BlockSerializer.model_validate(block)
        op = parsed.transactions[0].transaction.ops[0]
        assert isinstance(op, ChannelSetKeysOpSerializer)
        assert op.channel == bytes.fromhex(setkeys_sample["payload"]["channel"])
        assert len(op.keys) == len(setkeys_sample["payload"]["keys"])
        content = parsed.transactions[0].into_transaction().operations[0].content
        assert content.type == "ChannelSetKeys"
