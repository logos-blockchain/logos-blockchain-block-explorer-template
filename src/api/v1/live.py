from starlette.requests import Request
from starlette.responses import Response

from api.http import NDJsonStreamingResponse, query_int
from api.streams import into_tagged_ndjson_stream, merge_topics
from api.v1 import blocks, health, transactions


async def stream(request: Request) -> Response:
    """Every live feed a page shows, over one connection.

    Each line is `{"topic": "health" | "block" | "transaction", "data": ...}`.
    Health is always included; `blocks` and `transactions`, when given, subscribe
    to those feeds with that many items of history first, as their own streams do.
    Browsers open at most six HTTP/1.1 connections per host, and a stream per
    feed held three of them for every open tab.
    """
    topics = {"health": health.updates(request.app.state.node_api)}
    if "blocks" in request.query_params:
        topics["block"] = blocks.updates(request.app, query_int(request, "blocks", 0, ge=0, le=100))
    if "transactions" in request.query_params:
        topics["transaction"] = transactions.updates(request.app, query_int(request, "transactions", 0, ge=0, le=100))
    return NDJsonStreamingResponse(into_tagged_ndjson_stream(merge_topics(topics)))
