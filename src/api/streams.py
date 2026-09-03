import logging
from typing import AsyncIterable, AsyncIterator, List, Union

from core.models import NbeModel, NbeSchema

T = Union[NbeModel, NbeSchema]
Data = Union[T, List[T]]
Stream = AsyncIterator[Data]


logger = logging.getLogger(__name__)


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
