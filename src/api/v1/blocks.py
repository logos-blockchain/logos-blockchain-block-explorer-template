from http.client import NOT_FOUND
from typing import TYPE_CHECKING, AsyncIterator, List

from fastapi import Query
from rusty_results import Empty, Option, Some
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
) -> Response:
    blocks, total_count = await request.app.state.block_repository.get_paginated(page, page_size)
    total_pages = (total_count + page_size - 1) // page_size  # ceiling division

    return JSONResponse({
        "blocks": [BlockRead.from_block(block).model_dump(mode="json") for block in blocks],
        "page": page,
        "page_size": page_size,
        "total_count": total_count,
        "total_pages": total_pages,
    })


async def _get_blocks_stream_serialized(app: "NBE", block_from: Option[Block]) -> AsyncIterator[List[BlockRead]]:
    _stream = app.state.block_repository.updates_stream(block_from)
    async for blocks in _stream:
        yield [BlockRead.from_block(block) for block in blocks]


async def stream(request: NBERequest, prefetch_limit: int = Query(0, alias="prefetch-limit", ge=0)) -> Response:
    latest_blocks = await request.app.state.block_repository.get_latest(prefetch_limit)
    latest_block = Some(latest_blocks[-1]) if latest_blocks else Empty()
    bootstrap_blocks: List[BlockRead] = [BlockRead.from_block(block) for block in latest_blocks]

    blocks_stream: AsyncIterator[List[BlockRead]] = _get_blocks_stream_serialized(request.app, latest_block)
    ndjson_blocks_stream = into_ndjson_stream(blocks_stream, bootstrap_data=bootstrap_blocks)
    return NDJsonStreamingResponse(ndjson_blocks_stream)


async def get(request: NBERequest, block_hash: str) -> Response:
    if not block_hash:
        return Response(status_code=NOT_FOUND)
    block_hash = dehexify(block_hash)
    block = await request.app.state.block_repository.get_by_hash(block_hash)
    return block.map(lambda _block: JSONResponse(BlockRead.from_block(_block).model_dump(mode="json"))).unwrap_or_else(
        lambda: Response(status_code=NOT_FOUND)
    )
