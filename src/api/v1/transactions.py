from http.client import NOT_FOUND

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.http import NDJsonStreamingResponse, query_int
from api.streams import follow_chain, into_ndjson_stream
from api.v1.schemas import TransactionRead
from core.types import dehexify


async def stream(request: Request) -> Response:
    """The newest `prefetch-limit` canonical transactions, then every one whose block becomes canonical."""
    prefetch_limit = query_int(request, "prefetch-limit", 0, ge=0)
    db = request.app.state.db
    bootstrap = [TransactionRead.from_pair(*pair) for pair in db.latest_transactions(prefetch_limit)]
    after = db.max_canonical_seq()

    async def reads():
        async for pairs in follow_chain(
            request.app.state.notifier,
            db.transactions_since,
            after=after,
            cursor_of=lambda pair: pair[1].canonical_seq,
        ):
            yield [TransactionRead.from_pair(*pair) for pair in pairs]

    return NDJsonStreamingResponse(into_ndjson_stream(reads(), bootstrap_data=bootstrap))


async def list_transactions(request: Request) -> Response:
    page = query_int(request, "page", 0, ge=0)
    page_size = query_int(request, "page-size", 10, ge=1, le=100)
    pairs, total_count = request.app.state.db.paginated_transactions(page, page_size)
    total_pages = (total_count + page_size - 1) // page_size

    return JSONResponse(
        {
            "transactions": [TransactionRead.from_pair(*pair).model_dump(mode="json") for pair in pairs],
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        }
    )


async def get(request: Request) -> Response:
    """A transaction by hash: the canonical copy if there is one, else the copy in an orphaned block."""
    try:
        transaction_hash = dehexify(request.path_params["transaction_hash"])
    except ValueError:
        return Response(status_code=NOT_FOUND)
    pair = request.app.state.db.transaction_by_hash(transaction_hash)
    if pair is None:
        return Response(status_code=NOT_FOUND)
    return JSONResponse(TransactionRead.from_pair(*pair).model_dump(mode="json"))
