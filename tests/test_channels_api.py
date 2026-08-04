"""Tests for the channels activity aggregation behind /api/v1/channels/list."""

from types import SimpleNamespace

from api.v1.channels import aggregate_channels


def make_tx(tx_hash: bytes, height: int, contents: list) -> SimpleNamespace:
    """A minimal transaction-like object as consumed by aggregate_channels."""
    return SimpleNamespace(
        hash=tx_hash,
        block=SimpleNamespace(hash=bytes([height]) * 32, height=height, slot=height * 10),
        operations=[SimpleNamespace(content=content) for content in contents],
    )


def inscribe(channel: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        type="ChannelInscribe",
        channel_id=channel,
        model_dump=lambda mode: {"type": "ChannelInscribe", "channel_id": channel.hex()},
    )


def transfer() -> SimpleNamespace:
    return SimpleNamespace(type="LedgerTransfer")


CH_A = b"\xaa" * 32
CH_B = b"\xbb" * 32


def test_groups_by_channel_and_ranks_by_activity():
    transactions = [
        make_tx(b"\x03" * 32, height=3, contents=[inscribe(CH_A), transfer()]),
        make_tx(b"\x02" * 32, height=2, contents=[inscribe(CH_B)]),
        make_tx(b"\x01" * 32, height=1, contents=[inscribe(CH_A)]),
    ]

    channels = aggregate_channels(transactions, limit=8, ops_limit=25)

    assert [ch["channel_id"] for ch in channels] == [CH_A.hex(), CH_B.hex()]
    assert channels[0]["op_count"] == 2
    assert channels[0]["last_height"] == 3  # newest first
    assert [op["height"] for op in channels[0]["operations"]] == [3, 1]
    # Non-channel ops are excluded entirely.
    assert all(op["content"]["type"] == "ChannelInscribe" for ch in channels for op in ch["operations"])


def test_limits_channels_and_ops():
    transactions = [
        make_tx(bytes([i]) * 32, height=i, contents=[inscribe(CH_A), inscribe(CH_B)]) for i in range(9, 0, -1)
    ]

    channels = aggregate_channels(transactions, limit=1, ops_limit=3)

    assert len(channels) == 1
    top = channels[0]
    assert top["op_count"] == 9  # count covers everything scanned...
    assert len(top["operations"]) == 3  # ...but only ops_limit ops are returned
    assert [op["height"] for op in top["operations"]] == [9, 8, 7]


def test_channel_field_fallback_for_config_ops():
    # ChannelConfig uses "channel" rather than "channel_id".
    config = SimpleNamespace(
        type="ChannelConfig",
        channel=CH_A,
        model_dump=lambda mode: {"type": "ChannelConfig", "channel": CH_A.hex()},
    )
    # SimpleNamespace getattr default trick: ensure channel_id is absent.
    assert not hasattr(config, "channel_id")

    channels = aggregate_channels([make_tx(b"\x01" * 32, height=1, contents=[config])], limit=8, ops_limit=25)

    assert channels[0]["channel_id"] == CH_A.hex()
