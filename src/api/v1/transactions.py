from http.client import NOT_FOUND
from typing import TYPE_CHECKING, AsyncIterator, List

from fastapi import Query
from rusty_results import Empty, Option, Some
from starlette.responses import JSONResponse, Response

from api.streams import into_ndjson_stream
from api.v1.serializers.transactions import TransactionRead
from core.api import NBERequest, NDJsonStreamingResponse
from core.types import dehexify
from models.transactions.transaction import Transaction

if TYPE_CHECKING:
    from core.app import NBE


async def _get_transactions_stream_serialized(
    app: "NBE", transaction_from: Option[Transaction], *, fork: int
) -> AsyncIterator[List[TransactionRead]]:
    _stream = app.state.transaction_repository.updates_stream(transaction_from, fork=fork)
    async for transactions in _stream:
        yield [TransactionRead.from_transaction(transaction) for transaction in transactions]


async def stream(
    request: NBERequest,
    prefetch_limit: int = Query(0, alias="prefetch-limit", ge=0),
    fork: int = Query(...),
) -> Response:
    latest_transactions: List[Transaction] = await request.app.state.transaction_repository.get_latest(
        prefetch_limit, fork=fork, ascending=True, preload_relationships=True
    )
    latest_transaction = Some(latest_transactions[-1]) if latest_transactions else Empty()
    bootstrap_transactions = [TransactionRead.from_transaction(transaction) for transaction in latest_transactions]

    transactions_stream: AsyncIterator[List[TransactionRead]] = _get_transactions_stream_serialized(
        request.app, latest_transaction, fork=fork
    )
    ndjson_transactions_stream = into_ndjson_stream(transactions_stream, bootstrap_data=bootstrap_transactions)
    return NDJsonStreamingResponse(ndjson_transactions_stream)


async def list_transactions(
    request: NBERequest,
    page: int = Query(0, ge=0),
    page_size: int = Query(10, ge=1, le=100, alias="page-size"),
    fork: int = Query(...),
) -> Response:
    transactions, total_count = await request.app.state.transaction_repository.get_paginated(page, page_size, fork=fork)
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


async def get(request: NBERequest, transaction_hash: str, fork: int = Query(...)) -> Response:
    if not transaction_hash:
        return Response(status_code=NOT_FOUND)
    transaction_hash = dehexify(transaction_hash)
    transaction = await request.app.state.transaction_repository.get_by_hash(transaction_hash, fork=fork)
    return transaction.map(
        lambda _transaction: JSONResponse(TransactionRead.from_transaction(_transaction).model_dump(mode="json"))
    ).unwrap_or_else(lambda: Response(status_code=NOT_FOUND))
