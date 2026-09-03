"""Tests for node API serializers against the current (0.3.0-rc.2) wire format.

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
from node.api.serializers.operation import (
    ChannelConfigOpSerializer,
    ClaimPowRewardOpSerializer,
    LeaderClaimOpSerializer,
    SDPDeclareOpSerializer,
    UnknownOpSerializer,
)
from node.api.serializers.proof import Ed25519SignatureSerializer, NoneProofSerializer

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

    def test_021_format_with_state_and_phase(self):
        # 0.2.x nodes report "state" instead of "mode" and add a top-level "phase".
        payload = {
            "cryptarchia_info": {"lib": "aa", "lib_slot": 9, "tip": "bb", "slot": 10, "height": 3, "state": "Online"},
            "phase": "Following",
        }
        info = InfoSerializer.model_validate(normalize_info_payload(payload))
        assert info.mode == "Online"
        assert info.height == 3


class TestBaseUrl:
    @staticmethod
    def _base_url(host, port=8080, protocol="http") -> str:
        from types import SimpleNamespace

        from node.api.http import HttpNodeApi

        settings = SimpleNamespace(
            node_api_host=host, node_api_port=port, node_api_protocol=protocol, node_api_timeout=60, node_api_auth=None
        )
        return HttpNodeApi(settings).base_url

    def test_full_url_host_wins_over_protocol_and_port(self):
        url = self._base_url("https://devnet.blockchain.logos.co/node/1", port=8080, protocol="http")
        assert url == "https://devnet.blockchain.logos.co/node/1/"

    def test_host_with_path(self):
        assert self._base_url("example.com/node/1", port=0, protocol="https") == "https://example.com/node/1/"

    def test_plain_host_and_port(self):
        assert self._base_url("127.0.0.1", port=18080) == "http://127.0.0.1:18080"


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
        # A malformed op payload plus the legacy "NoProof" marker must not
        # break ingestion: the op degrades to UnknownOp, the proof to None.
        tx = block["transactions"][0]
        tx["mantle_tx"]["ops"][0] = {"opcode": 48, "payload": {"rewards_root": "aa" * 32}}
        tx["ops_proofs"][0] = "NoProof"
        parsed = BlockSerializer.model_validate(block)
        operation = parsed.transactions[0].into_transaction().operations[0]
        assert operation.content.type == "UnknownOp"
        assert operation.content.opcode == 48
        assert operation.proof.type == "None"

    def test_unknown_tagged_proof_is_preserved_not_fatal(self, block):
        tx = block["transactions"][0]
        tx["ops_proofs"][0] = {"FutureProof": {"bytes": "aa"}}
        parsed = BlockSerializer.model_validate(block)
        operation = parsed.transactions[0].into_transaction().operations[0]
        assert operation.proof.type == "Unknown"
        assert operation.proof.raw == {"FutureProof": {"bytes": "aa"}}


class TestChannelConfigOp:
    """Opcode 16 is ChannelConfig on 0.2.x nodes (previously set-keys)."""

    def test_channel_config_parses(self, block):
        payload = {
            "channel": "ab" * 32,
            "keys": ["cd" * 32],
            "posting_timeframe": 10,
            "posting_timeout": 20,
            "configuration_threshold": 1,
            "transfer_threshold": 2,
        }
        tx = block["transactions"][0]
        tx["mantle_tx"]["ops"] = [{"opcode": 16, "payload": payload}]
        tx["ops_proofs"] = [
            {"ChannelMultiSigProof": {"signatures": [{"signature": "ee" * 64, "channel_key_index": 0}]}}
        ]
        parsed = BlockSerializer.model_validate(block)
        op = parsed.transactions[0].transaction.ops[0]
        assert isinstance(op, ChannelConfigOpSerializer)
        assert op.channel == bytes.fromhex(payload["channel"])
        assert op.transfer_threshold == 2
        operation = parsed.transactions[0].into_transaction().operations[0]
        assert operation.content.type == "ChannelConfig"
        assert operation.proof.type == "ChannelMultiSig"
        assert operation.proof.signatures[0].channel_key_index == 0


class TestNewOps:
    """Ops introduced with the 0.2.x wire format."""

    def test_leader_claim_with_poc_proof(self, block):
        tx = block["transactions"][0]
        tx["mantle_tx"]["ops"] = [
            {"opcode": 48, "payload": {"rewards_root": "aa" * 32, "voucher_nullifier": "bb" * 32, "pk": "cc" * 32}}
        ]
        tx["ops_proofs"] = [{"PoC": {"proof": "dd" * 128}}]
        parsed = BlockSerializer.model_validate(block)
        op = parsed.transactions[0].transaction.ops[0]
        assert isinstance(op, LeaderClaimOpSerializer)
        operation = parsed.transactions[0].into_transaction().operations[0]
        assert operation.content.type == "LeaderClaim"
        assert operation.content.pk == bytes.fromhex("cc" * 32)
        assert operation.proof.type == "PoC"
        assert len(operation.proof.proof) == 128

    @pytest.mark.parametrize(
        ("opcode", "payload", "expected_type"),
        [
            (18, {"channel_id": "aa" * 32, "inputs": ["bb" * 32], "metadata": "beef"}, "ChannelDeposit"),
            (19, {"channel_id": "aa" * 32, "inputs": ["bb" * 32]}, "ChannelWithdraw"),
            (
                20,
                {"channel_id": "aa" * 32, "inputs": ["bb" * 32], "outputs": [{"value": 7, "pk": "cc" * 32}]},
                "ChannelTransfer",
            ),
            (33, {"declaration_id": "aa" * 32, "nonce": 4, "locked_note_id": "bb" * 32}, "SDPWithdraw"),
        ],
        ids=["deposit", "withdraw", "channel-transfer", "sdp-withdraw"],
    )
    def test_new_op_parses(self, block, opcode, payload, expected_type):
        tx = block["transactions"][0]
        tx["mantle_tx"]["ops"] = [{"opcode": opcode, "payload": payload}]
        tx["ops_proofs"] = [{"Ed25519Sig": "ee" * 64}]
        parsed = BlockSerializer.model_validate(block)
        content = parsed.transactions[0].into_transaction().operations[0].content
        assert content.type == expected_type


class TestNode030WireFormat:
    """Changes introduced with node 0.3.0-rc.2 (devnet reset of 2026-09)."""

    def test_header_body_root_is_accepted(self, block):
        # 0.3.0 renamed block_root -> body_root and added uncle_headers.
        header = block["header"]
        header["body_root"] = header.pop("block_root")
        block["uncle_headers"] = []
        parsed = BlockSerializer.model_validate(block)
        assert parsed.header.block_root == bytes.fromhex(header["body_root"])
        assert parsed.into_block().block_root == bytes.fromhex(header["body_root"])

    def test_header_legacy_block_root_still_accepted(self, block):
        assert BlockSerializer.model_validate(block).header.block_root == bytes.fromhex(block["header"]["block_root"])

    def test_claim_pow_reward_with_none_proof(self, block):
        tx = block["transactions"][0]
        tx["mantle_tx"]["ops"] = [
            {
                "opcode": 64,
                "payload": {
                    "epoch_nonce": "aa" * 32,
                    "block_hash": list(range(32)),  # plain [u8; 32] serializes as an int array
                    "public_key": "cc" * 32,
                },
            }
        ]
        tx["ops_proofs"] = [{"None": None}]
        parsed = BlockSerializer.model_validate(block)
        op = parsed.transactions[0].transaction.ops[0]
        assert isinstance(op, ClaimPowRewardOpSerializer)
        assert isinstance(parsed.transactions[0].operations_proofs[0], NoneProofSerializer)
        operation = parsed.transactions[0].into_transaction().operations[0]
        assert operation.content.type == "ClaimPowReward"
        assert operation.content.block_hash == bytes(range(32))
        assert operation.content.public_key == bytes.fromhex("cc" * 32)
        assert operation.proof.type == "None"
        # Round-trips through the JSON column representation.
        dumped = operation.model_dump(mode="json")
        assert dumped["content"]["block_hash"] == bytes(range(32)).hex()
        assert dumped["proof"] == {"type": "None"}

    @pytest.mark.parametrize("field", ["service_note_id", "locked_note_id"], ids=["0.3.0", "0.2.x"])
    def test_sdp_declare_note_field_rename(self, block, field):
        tx = block["transactions"][0]
        tx["mantle_tx"]["ops"] = [
            {
                "opcode": 32,
                "payload": {
                    "service_type": "BN",
                    "locators": ["/ip4/127.0.0.1/udp/3000/quic-v1"],
                    "provider_id": "aa" * 32,
                    "zk_id": "bb" * 32,
                    field: "cc" * 32,
                },
            }
        ]
        tx["ops_proofs"] = [
            {
                "ZkAndEd25519Sigs": {
                    "zk_sig": {"pi_a": "01" * 32, "pi_b": "02" * 64, "pi_c": "03" * 32},
                    "ed25519_sig": "04" * 64,
                }
            }
        ]
        parsed = BlockSerializer.model_validate(block)
        assert isinstance(parsed.transactions[0].transaction.ops[0], SDPDeclareOpSerializer)
        content = parsed.transactions[0].into_transaction().operations[0].content
        assert content.type == "SDPDeclare"
        assert content.service_note_id == bytes.fromhex("cc" * 32)
        assert content.model_dump(mode="json")["service_note_id"] == "cc" * 32

    @pytest.mark.parametrize("field", ["service_note_id", "locked_note_id"], ids=["0.3.0", "0.2.x"])
    def test_sdp_withdraw_note_field_rename(self, block, field):
        tx = block["transactions"][0]
        tx["mantle_tx"]["ops"] = [
            {"opcode": 33, "payload": {"declaration_id": "aa" * 32, "nonce": 4, field: "bb" * 32}}
        ]
        tx["ops_proofs"] = [{"ZkSig": {"pi_a": "01" * 32, "pi_b": "02" * 64, "pi_c": "03" * 32}}]
        content = BlockSerializer.model_validate(block).transactions[0].into_transaction().operations[0].content
        assert content.type == "SDPWithdraw"
        assert content.service_note_id == bytes.fromhex("bb" * 32)

    def test_channel_config_parent(self, block):
        payload = {
            "channel": "ab" * 32,
            "parent": "00" * 32,
            "keys": ["cd" * 32],
            "posting_timeframe": 10,
            "posting_timeout": 20,
            "configuration_threshold": 1,
            "transfer_threshold": 2,
        }
        tx = block["transactions"][0]
        tx["mantle_tx"]["ops"] = [{"opcode": 16, "payload": payload}]
        tx["ops_proofs"] = [{"ChannelMultiSigProof": {"signatures": []}}]
        content = BlockSerializer.model_validate(block).transactions[0].into_transaction().operations[0].content
        assert content.type == "ChannelConfig"
        assert content.parent == b"\x00" * 32

    def test_legacy_db_rows_without_new_fields_still_load(self):
        from models.transactions.operations.operation import Operation

        legacy_config = Operation.model_validate(
            {
                "content": {
                    "type": "ChannelConfig",
                    "channel": "ab" * 32,
                    "keys": [],
                    "posting_timeframe": 1,
                    "posting_timeout": 1,
                    "configuration_threshold": 1,
                    "transfer_threshold": 1,
                },
                "proof": {"type": "ChannelMultiSig", "signatures": []},
            }
        )
        assert legacy_config.content.parent is None

        legacy_declare = Operation.model_validate(
            {
                "content": {
                    "type": "SDPDeclare",
                    "service_type": "BN",
                    "locators": [],
                    "provider_id": "aa" * 32,
                    "zk_id": "bb" * 32,
                    "locked_note_id": "cc" * 32,
                },
                "proof": {"type": "Zk", "signature": "00"},
            }
        )
        assert legacy_declare.content.service_note_id == bytes.fromhex("cc" * 32)
