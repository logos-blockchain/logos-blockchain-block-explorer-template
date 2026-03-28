from asyncio import sleep
from typing import AsyncIterator

from starlette.responses import JSONResponse, Response

from api.streams import into_ndjson_stream
from core.api import NBERequest, NDJsonStreamingResponse
from models.health import Health
from node.api.base import NodeApi
from node.api.serializers.health import HealthSerializer


async def get(request: NBERequest) -> Response:
    response = await request.app.state.node_api.get_health()
    # HealthSerializer needs to be converted to dict for JSON serialization
    if hasattr(response, 'model_dump'):
        return JSONResponse(response.model_dump(mode='json'))
    return JSONResponse(response)


async def _create_health_stream(node_api: NodeApi, *, poll_interval_seconds: int = 10) -> AsyncIterator[Health]:
    while True:
        health_serializer: HealthSerializer = await node_api.get_health()
        yield health_serializer.into_health()
        await sleep(poll_interval_seconds)


async def stream(request: NBERequest) -> Response:
    health_stream = _create_health_stream(request.app.state.node_api)
    ndjson_health_stream = into_ndjson_stream(health_stream)
    return NDJsonStreamingResponse(ndjson_health_stream)
