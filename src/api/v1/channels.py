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


def collect_channel_operations(transactions_oldest_first, channel_id: str) -> list[dict]:
    """All operations for one channel, oldest-first, with a stable `index` per op.

    Indices are relative to the scanned window (see SCAN_TRANSACTION_LIMIT), so
    index 0 is the oldest operation the explorer still has in view.
    """
    wanted = channel_id.lower()
    operations: list[dict] = []
    for tx in transactions_oldest_first:
        for operation in tx.operations:
            content = operation.content
            if content.type not in CHANNEL_CONTENT_TYPES:
                continue
            found = _channel_id_of(content)
            if found is None or found.lower() != wanted:
                continue
            operations.append(
                {
                    "index": len(operations),
                    "transaction_hash": tx.hash.hex(),
                    "block_hash": tx.block.hash.hex(),
                    "height": tx.block.height,
                    "slot": tx.block.slot,
                    "content": content.model_dump(mode="json"),
                }
            )
    return operations


async def get_channel(
    request: NBERequest,
    channel_id: str,
    fork: int = Query(...),
    page: int = Query(0, ge=0),
    page_size: int = Query(25, ge=1, le=100, alias="page-size"),
) -> Response:
    """One channel's operations, oldest-first, paginated."""
    transactions = await request.app.state.transaction_repository.get_latest(
        SCAN_TRANSACTION_LIMIT, fork=fork, ascending=True, preload_relationships=True
    )

    operations = collect_channel_operations(transactions, channel_id)
    start = page * page_size

    return JSONResponse(
        {
            "channel_id": channel_id,
            "op_count": len(operations),
            "page": page,
            "page_size": page_size,
            "operations": operations[start : start + page_size],
            "scanned_transactions": len(transactions),
        }
    )


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
