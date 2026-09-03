import logging
from typing import AsyncIterable, AsyncIterator, Awaitable, Callable, List, Sequence, TypeVar, Union

from core.models import NbeModel, NbeSchema
from core.notifier import ChainNotifier

T = Union[NbeModel, NbeSchema]
Data = Union[T, List[T]]
Stream = AsyncIterator[Data]

# How long a stream waits for a change notification before re-checking the
# database anyway. Keeps a stream alive across a missed notification.
STREAM_RECHECK_SECONDS = 15.0

logger = logging.getLogger(__name__)
Row = TypeVar("Row")


def _ndjson_line(item: T) -> bytes:
    return f"{item.model_dump_json()}\n".encode()


def _into_ndjson_data(data: Data) -> bytes:
    if isinstance(data, list):
        return b"".join(_ndjson_line(item) for item in data)
    return _ndjson_line(data)


async def into_ndjson_stream(stream: Stream, *, bootstrap_data: Data = None) -> AsyncIterable[bytes]:
    if bootstrap_data is not None:
        ndjson_data = _into_ndjson_data(bootstrap_data)
        if ndjson_data:
            yield ndjson_data
        else:
            logger.debug("Ignoring streaming bootstrap data because it is empty.")

    async for data in stream:
        ndjson_data = _into_ndjson_data(data)
        if ndjson_data:
            yield ndjson_data
        else:
            logger.debug("Ignoring streaming data because it is empty.")


async def follow_chain(
    notifier: ChainNotifier,
    fetch_since: Callable[[int], Awaitable[Sequence[Row]]],
    *,
    after_id: int,
) -> AsyncIterator[List[Row]]:
    """Yield batches of rows with id > cursor as ingestion commits them.

    `fetch_since(cursor)` must return rows ordered by id. The notifier version
    is read before each fetch so a commit landing between the fetch and the
    wait is never missed.
    """
    cursor = after_id
    while True:
        version = notifier.version
        rows = await fetch_since(cursor)
        if rows:
            cursor = rows[-1].id
            yield list(rows)
            continue
        await notifier.wait_for_change(version, timeout=STREAM_RECHECK_SECONDS)
