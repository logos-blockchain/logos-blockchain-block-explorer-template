from http.client import BAD_REQUEST

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.http import query_int
from db import ChannelOperationRow

CHANNEL_ID_BYTES = 32
# The overview shows a one-line preview per op; inscriptions run to hundreds of KB.
INSCRIPTION_PREVIEW_BYTES = 128


def _parse_channel_id(raw: str) -> bytes | None:
    cleaned = raw.strip().lower().removeprefix("0x")
    try:
        channel_id = bytes.fromhex(cleaned)
    except ValueError:
        return None
    return channel_id if len(channel_id) == CHANNEL_ID_BYTES else None


def _preview(content: dict) -> dict:
    """An op's content for the overview: an inscription cut to its head, with its full size alongside."""
    if content["type"] != "ChannelInscribe":
        return content
    inscription = content["inscription"]  # hex
    return {
        **content,
        "inscription": inscription[: INSCRIPTION_PREVIEW_BYTES * 2],
        "inscription_size": len(inscription) // 2,
    }


def serialize_operation(row: ChannelOperationRow, *, index: int | None = None) -> dict | None:
    """API shape for one indexed channel op; None if the row no longer matches its transaction."""
    channel_op, transaction, block = row
    if channel_op.op_index >= len(transaction.operations):
        return None
    content = transaction.operations[channel_op.op_index].content
    payload = {
        "transaction_hash": transaction.hash.hex(),
        "block_hash": block.hash.hex(),
        "height": block.height,
        "slot": block.slot,
        "content": content.model_dump(mode="json"),
    }
    if index is not None:
        payload = {"index": index, **payload}
    return payload


async def get_channel(request: Request) -> Response:
    """One channel's operations across its whole history on the canonical chain, oldest-first, paginated.

    `index` is the op's position in that history, so it is stable across pages
    and refreshes (barring a reorg).
    """
    page = query_int(request, "page", 0, ge=0)
    page_size = query_int(request, "page-size", 25, ge=1, le=100)
    parsed = _parse_channel_id(request.path_params["channel_id"])
    if parsed is None:
        return JSONResponse(
            {"detail": f"channel_id must be {CHANNEL_ID_BYTES} bytes of hex ({CHANNEL_ID_BYTES * 2} characters)"},
            status_code=BAD_REQUEST,
        )

    db = request.app.state.db
    op_count = db.channel_op_count(parsed)
    offset = page * page_size
    rows = db.channel_operations(parsed, newest_first=False, offset=offset, limit=page_size)

    operations = []
    for position, row in enumerate(rows):
        serialized = serialize_operation(row, index=offset + position)
        if serialized is not None:
            operations.append(serialized)

    return JSONResponse(
        {
            "channel_id": parsed.hex(),
            "op_count": op_count,
            "page": page,
            "page_size": page_size,
            "operations": operations,
        }
    )


async def list_channels(request: Request) -> Response:
    """Top channels by total activity on the canonical chain, each with its most recent operations.

    Inscriptions are cut to a preview (see `_preview`); the channel's own page has them in full.
    """
    limit = query_int(request, "limit", 8, ge=1, le=24)
    ops_limit = query_int(request, "ops-limit", 25, ge=1, le=100)
    db = request.app.state.db

    def build() -> dict:
        channels = []
        for channel_id, op_count, _last_height in db.top_channels(limit=limit):
            rows = db.channel_operations(channel_id, newest_first=True, limit=ops_limit)
            operations = [op for op in (serialize_operation(row) for row in rows) if op is not None]
            if not operations:
                continue
            for op in operations:
                op["content"] = _preview(op["content"])
            channels.append(
                {
                    "channel_id": channel_id.hex(),
                    "op_count": op_count,
                    "last_height": operations[0]["height"],
                    "last_slot": operations[0]["slot"],
                    "operations": operations,
                }
            )
        return {"channels": channels}

    return request.app.state.etag.respond(request, build)
