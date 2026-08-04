from fastapi import Query
from starlette.responses import JSONResponse, Response

from core.api import NBERequest

# Content types that belong to a channel. ChannelSetKeys/ChannelBlob are
# legacy (pre-0.2.x) types kept so old rows still show up.
CHANNEL_CONTENT_TYPES = {
    "ChannelInscribe",
    "ChannelConfig",
    "ChannelDeposit",
    "ChannelWithdraw",
    "ChannelTransfer",
    "ChannelSetKeys",
    "ChannelBlob",
}

# Channel activity is aggregated in Python from the operations JSON of recent
# transactions; this caps how many transactions are scanned per request.
SCAN_TRANSACTION_LIMIT = 2000


def _channel_id_of(content) -> str | None:
    channel = getattr(content, "channel_id", None)
    if channel is None:
        channel = getattr(content, "channel", None)
    if channel is None:
        return None
    return channel.hex() if isinstance(channel, bytes) else str(channel)


def aggregate_channels(transactions_newest_first, limit: int, ops_limit: int) -> list[dict]:
    """Group channel operations by channel id; top `limit` channels by op count."""
    channels: dict[str, dict] = {}
    for tx in transactions_newest_first:
        for operation in tx.operations:
            content = operation.content
            if content.type not in CHANNEL_CONTENT_TYPES:
                continue
            channel_id = _channel_id_of(content)
            if channel_id is None:
                continue

            channel = channels.setdefault(
                channel_id,
                {
                    "channel_id": channel_id,
                    "op_count": 0,
                    "last_height": tx.block.height,
                    "last_slot": tx.block.slot,
                    "operations": [],
                },
            )
            channel["op_count"] += 1
            if len(channel["operations"]) < ops_limit:
                channel["operations"].append(
                    {
                        "transaction_hash": tx.hash.hex(),
                        "block_hash": tx.block.hash.hex(),
                        "height": tx.block.height,
                        "slot": tx.block.slot,
                        "content": content.model_dump(mode="json"),
                    }
                )

    return sorted(channels.values(), key=lambda ch: (-ch["op_count"], -ch["last_height"]))[:limit]


async def list_channels(
    request: NBERequest,
    fork: int = Query(...),
    limit: int = Query(8, ge=1, le=24),
    ops_limit: int = Query(25, ge=1, le=100, alias="ops-limit"),
) -> Response:
    """Top channels by activity, each with its most recent operations."""
    transactions = await request.app.state.transaction_repository.get_latest(
        SCAN_TRANSACTION_LIMIT, fork=fork, ascending=True, preload_relationships=True
    )

    # get_latest(ascending=True) returns oldest-first; aggregate newest-first so
    # per-channel operations accumulate newest-first.
    top = aggregate_channels(reversed(transactions), limit=limit, ops_limit=ops_limit)

    return JSONResponse(
        {
            "channels": top,
            "scanned_transactions": len(transactions),
        }
    )
