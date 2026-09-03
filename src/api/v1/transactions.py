from http.client import NOT_FOUND
from typing import List

from fastapi import Query
from starlette.responses import JSONResponse, Response

from api.streams import follow_chain, into_ndjson_stream
from api.v1.serializers.transactions import TransactionRead
from core.api import NBERequest, NDJsonStreamingResponse
from core.types import dehexify


async def stream(
    request: NBERequest,
    prefetch_limit: int = Query(0, alias="prefetch-limit", ge=0),
) -> Response:
    """The newest `prefetch-limit` canonical transactions, then every new one as it is ingested."""
    repository = request.app.state.transaction_repository
    latest = await repository.get_latest(prefetch_limit)
    bootstrap: List[TransactionRead] = [TransactionRead.from_transaction(transaction) for transaction in latest]
    after_id = max((transaction.id for transaction in latest), default=0)

    async def reads():
        async for transactions in follow_chain(
            request.app.state.chain_notifier, repository.get_since, after_id=after_id
        ):
            yield [TransactionRead.from_transaction(transaction) for transaction in transactions]

    return NDJsonStreamingResponse(into_ndjson_stream(reads(), bootstrap_data=bootstrap))


async def list_transactions(
    request: NBERequest,
    page: int = Query(0, ge=0),
    page_size: int = Query(10, ge=1, le=100, alias="page-size"),
) -> Response:
    transactions, total_count = await request.app.state.transaction_repository.get_paginated(page, page_size)
    total_pages = (total_count + page_size - 1) // page_size

    return JSONResponse(
        {
            "transactions": [TransactionRead.from_transaction(tx).model_dump(mode="json") for tx in transactions],
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
        }
    )


async def get(request: NBERequest, transaction_hash: str) -> Response:
    try:
        transaction_hash = dehexify(transaction_hash)
    except ValueError:
        return Response(status_code=NOT_FOUND)
    transaction = await request.app.state.transaction_repository.get_by_hash(transaction_hash)
    if transaction is None:
        return Response(status_code=NOT_FOUND)
    return JSONResponse(TransactionRead.from_transaction(transaction).model_dump(mode="json"))
