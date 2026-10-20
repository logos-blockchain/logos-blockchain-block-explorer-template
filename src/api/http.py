import os
from http.client import BAD_REQUEST, NOT_MODIFIED
from typing import Any, Callable, Dict, Optional

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import ContentStream, JSONResponse, Response, StreamingResponse

from core.notifier import ChainNotifier


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


class ChainVersionCache:
    """JSON bodies of read endpoints, kept until ingestion next changes the canonical chain.

    Every canonical change bumps the notifier's version, so a body built at one
    version stays correct until the version moves. The version is also the ETag,
    so a client polling an unchanged chain gets a bodiless 304 without a query.
    """

    MAX_ENTRIES = 32  # distinct query strings per version; past this, bodies are built but not kept

    def __init__(self, notifier: ChainNotifier) -> None:
        self.notifier = notifier
        # Versions restart at zero with the process; keep a new process's ETags distinct.
        self._boot = os.urandom(4).hex()
        self._version: Optional[int] = None
        self._bodies: Dict[str, bytes] = {}

    def respond(self, request: Request, build: Callable[[], Any]) -> Response:
        version = self.notifier.version
        etag = f'"{self._boot}-{version}"'
        headers = {"ETag": etag, "Cache-Control": "no-cache"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=NOT_MODIFIED, headers=headers)
        if version != self._version:
            self._version, self._bodies = version, {}
        key = f"{request.url.path}?{request.url.query}"
        body = self._bodies.get(key)
        if body is None:
            body = JSONResponse(build()).body
            if len(self._bodies) < self.MAX_ENTRIES:
                self._bodies[key] = body
        return Response(body, media_type="application/json", headers=headers)
