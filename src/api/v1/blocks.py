from http.client import NOT_FOUND
from typing import List

from fastapi import Query
from starlette.responses import JSONResponse, Response

from api.streams import follow_chain, into_ndjson_stream
from api.v1.serializers.blocks import BlockRead, BlockSummary
from core.api import NBERequest, NDJsonStreamingResponse
from core.types import dehexify


async def list_blocks(
    request: NBERequest,
    page: int = Query(0, ge=0),
    page_size: int = Query(10, ge=1, le=100, alias="page-size"),
) -> Response:
    blocks, total_count = await request.app.state.block_repository.get_paginated(page, page_size)
    total_pages = (total_count + page_size - 1) // page_size  # ceiling division

    return JSONResponse(
        {
            "blocks": [BlockSummary.from_block(block).model_dump(mode="json") for block in blocks],
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        }
    )


async def stream(
    request: NBERequest,
    prefetch_limit: int = Query(0, alias="prefetch-limit", ge=0),
) -> Response:
    """The newest `prefetch-limit` canonical blocks, then every block that becomes canonical from now on."""
    repository = request.app.state.block_repository
    latest_blocks = await repository.get_latest(prefetch_limit)
    bootstrap: List[BlockSummary] = [BlockSummary.from_block(block) for block in latest_blocks]
    after = await repository.max_canonical_seq()

    async def summaries():
        async for blocks in follow_chain(
            request.app.state.chain_notifier,
            repository.get_since,
            after=after,
            cursor_of=lambda block: block.canonical_seq,
        ):
            yield [BlockSummary.from_block(block) for block in blocks]

    return NDJsonStreamingResponse(into_ndjson_stream(summaries(), bootstrap_data=bootstrap))


async def get(request: NBERequest, block_hash: str) -> Response:
    try:
        block_hash = dehexify(block_hash)
    except ValueError:
        return Response(status_code=NOT_FOUND)
    block = await request.app.state.block_repository.get_by_hash(block_hash)
    if block is None:
        return Response(status_code=NOT_FOUND)
    return JSONResponse(BlockRead.from_block(block).model_dump(mode="json"))
