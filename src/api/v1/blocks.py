from http.client import NOT_FOUND

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.http import NDJsonStreamingResponse, query_int
from api.streams import follow_chain, into_ndjson_stream
from api.v1.schemas import BlockRead, BlockSummary
from core.types import dehexify


async def list_blocks(request: Request) -> Response:
    page = query_int(request, "page", 0, ge=0)
    page_size = query_int(request, "page-size", 10, ge=1, le=100)
    blocks, total_count = request.app.state.db.paginated_blocks(page, page_size)
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


async def stream(request: Request) -> Response:
    """The newest `prefetch-limit` canonical blocks, then every block that becomes canonical from now on."""
    prefetch_limit = query_int(request, "prefetch-limit", 0, ge=0)
    db = request.app.state.db
    bootstrap = [BlockSummary.from_block(block) for block in db.latest_blocks(prefetch_limit)]
    after = db.max_canonical_seq()

    async def summaries():
        async for blocks in follow_chain(
            request.app.state.notifier,
            db.blocks_since,
            after=after,
            cursor_of=lambda block: block.canonical_seq,
        ):
            yield [BlockSummary.from_block(block) for block in blocks]

    return NDJsonStreamingResponse(into_ndjson_stream(summaries(), bootstrap_data=bootstrap))


async def get(request: Request) -> Response:
    try:
        block_hash = dehexify(request.path_params["block_hash"])
    except ValueError:
        return Response(status_code=NOT_FOUND)
    block = request.app.state.db.block_by_hash(block_hash)
    if block is None:
        return Response(status_code=NOT_FOUND)
    return JSONResponse(BlockRead.from_block(block).model_dump(mode="json"))
