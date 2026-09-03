from asyncio import sleep
from typing import AsyncIterator

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.http import NDJsonStreamingResponse
from api.streams import into_ndjson_stream
from models.health import Health
from node.api.http import HttpNodeApi


async def get(request: Request) -> Response:
    health = await request.app.state.node_api.get_health()
    return JSONResponse(health.model_dump())


async def _health_stream(node_api: HttpNodeApi, *, poll_interval_seconds: int = 10) -> AsyncIterator[Health]:
    while True:
        yield await node_api.get_health()
        await sleep(poll_interval_seconds)


async def stream(request: Request) -> Response:
    return NDJsonStreamingResponse(into_ndjson_stream(_health_stream(request.app.state.node_api)))
