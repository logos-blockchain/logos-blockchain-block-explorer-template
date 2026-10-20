import asyncio
import logging
from typing import AsyncIterable, AsyncIterator, Callable, Dict, List, Sequence, Tuple, TypeVar, Union

from core.models import LbeSchema
from core.notifier import ChainNotifier

Data = Union[LbeSchema, List[LbeSchema]]
Stream = AsyncIterator[Data]

# How long a stream waits for a change notification before re-checking the
# database anyway. Keeps a stream alive across a missed notification.
STREAM_RECHECK_SECONDS = 15.0

logger = logging.getLogger(__name__)
Row = TypeVar("Row")


def _ndjson_line(item: LbeSchema) -> bytes:
    return f"{item.model_dump_json()}\n".encode()


def _into_ndjson_data(data: Data) -> bytes:
    if isinstance(data, list):
        return b"".join(_ndjson_line(item) for item in data)
    return _ndjson_line(data)


async def into_ndjson_stream(stream: Stream) -> AsyncIterable[bytes]:
    async for data in stream:
        ndjson_data = _into_ndjson_data(data)
        if ndjson_data:
            yield ndjson_data
        else:
            logger.debug("Ignoring streaming data because it is empty.")


async def follow_chain(
    notifier: ChainNotifier,
    fetch_since: Callable[[int], Sequence[Row]],
    *,
    after: int,
    cursor_of: Callable[[Row], int],
) -> AsyncIterator[List[Row]]:
    """Yield batches of rows past a cursor as ingestion commits them.

    `fetch_since(cursor)` must return rows in ascending `cursor_of` order. The
    cursor is the canonical sequence (see the block table), so a block that
    becomes canonical in a reorg is delivered even if its row id is old. The
    notifier version is read before each fetch so a commit landing between the
    fetch and the wait is never missed.
    """
    cursor = after
    while True:
        version = notifier.version
        rows = fetch_since(cursor)
        if rows:
            cursor = max(cursor_of(row) for row in rows)
            yield list(rows)
            continue
        await notifier.wait_for_change(version, timeout=STREAM_RECHECK_SECONDS)


async def merge_topics(streams: Dict[str, Stream]) -> AsyncIterator[Tuple[str, Data]]:
    """Interleave several streams into (topic, data) pairs, as each produces.

    If any stream fails, the merged stream fails with it; the others are cancelled.
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def pump(topic: str, stream: Stream) -> None:
        try:
            async for data in stream:
                await queue.put((topic, data, None))
        except Exception as error:
            await queue.put((topic, None, error))

    tasks = [asyncio.create_task(pump(topic, stream)) for topic, stream in streams.items()]
    try:
        while True:
            topic, data, error = await queue.get()
            if error is not None:
                raise error
            yield topic, data
    finally:
        for task in tasks:
            task.cancel()


async def into_tagged_ndjson_stream(stream: AsyncIterator[Tuple[str, Data]]) -> AsyncIterable[bytes]:
    """One `{"topic": ..., "data": ...}` line per item."""
    async for topic, data in stream:
        items = data if isinstance(data, list) else [data]
        if items:
            yield b"".join(f'{{"topic":"{topic}","data":{item.model_dump_json()}}}\n'.encode() for item in items)
