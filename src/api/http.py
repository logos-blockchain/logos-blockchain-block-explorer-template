from http.client import BAD_REQUEST
from typing import Optional

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import ContentStream, StreamingResponse


def query_int(request: Request, name: str, default: int, *, ge: Optional[int] = None, le: Optional[int] = None) -> int:
    """An integer query parameter, bounds-checked; 400 when malformed or out of range."""
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise HTTPException(BAD_REQUEST, f"{name} must be an integer")
    if ge is not None and value < ge:
        raise HTTPException(BAD_REQUEST, f"{name} must be >= {ge}")
    if le is not None and value > le:
        raise HTTPException(BAD_REQUEST, f"{name} must be <= {le}")
    return value


class NDJsonStreamingResponse(StreamingResponse):
    def __init__(self, content: ContentStream):
        super().__init__(
            content,
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
