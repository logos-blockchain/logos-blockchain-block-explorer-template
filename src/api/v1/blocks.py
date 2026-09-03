from http.client import NOT_FOUND
from typing import TYPE_CHECKING, AsyncIterator, List, Optional

from fastapi import Query
from starlette.responses import JSONResponse, Response

from api.streams import into_ndjson_stream
from api.v1.serializers.blocks import BlockRead
from core.api import NBERequest, NDJsonStreamingResponse
from core.types import dehexify
from models.block import Block

if TYPE_CHECKING:
    from core.app import NBE


async def list_blocks(
    request: NBERequest,
    page: int = Query(0, ge=0),
    page_size: int = Query(10, ge=1, le=100, alias="page-size"),
    fork: int = Query(...),
) -> Response:
    blocks, total_count = await request.app.state.block_repository.get_paginated(page, page_size, fork=fork)
    total_pages = (total_count + page_size - 1) // page_size  # ceiling division

    return JSONResponse(
        {
            "blocks": [BlockRead.from_block(block).model_dump(mode="json") for block in blocks],
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        }
    )


async def _get_blocks_stream_serialized(
    app: "NBE", block_from: Optional[Block], *, fork: int
) -> AsyncIterator[List[BlockRead]]:
    _stream = app.state.block_repository.updates_stream(block_from, fork=fork)
    async for blocks in _stream:
        yield [BlockRead.from_block(block) for block in blocks]


async def stream(
    request: NBERequest,
    prefetch_limit: int = Query(0, alias="prefetch-limit", ge=0),
    fork: int = Query(...),
) -> Response:
    latest_blocks = await request.app.state.block_repository.get_latest(prefetch_limit, fork=fork)
    latest_block = latest_blocks[-1] if latest_blocks else None
    bootstrap_blocks: List[BlockRead] = [BlockRead.from_block(block) for block in latest_blocks]

    blocks_stream: AsyncIterator[List[BlockRead]] = _get_blocks_stream_serialized(request.app, latest_block, fork=fork)
    ndjson_blocks_stream = into_ndjson_stream(blocks_stream, bootstrap_data=bootstrap_blocks)
    return NDJsonStreamingResponse(ndjson_blocks_stream)


async def get(request: NBERequest, block_hash: str) -> Response:
    try:
        block_hash = dehexify(block_hash)
    except ValueError:
        return Response(status_code=NOT_FOUND)
    block = await request.app.state.block_repository.get_by_hash(block_hash)
    if block is None:
        return Response(status_code=NOT_FOUND)
    return JSONResponse(BlockRead.from_block(block).model_dump(mode="json"))
