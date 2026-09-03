from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from api.v1 import blocks, channels, health, notes, transactions
from core.notifier import ChainNotifier
from core.settings import Settings
from db import Database
from frontend import spa, static_files
from node.api.http import HttpNodeApi
from node.ingestion import run_ingestion


async def api_index(_request: Request) -> JSONResponse:
    return JSONResponse({"version": "1"})


async def http_exception(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


ROUTES = [
    Mount("/static", static_files, name="static"),
    Route("/api/v1/", api_index, methods=["GET", "HEAD"]),
    Route("/api/v1/health/stream", health.stream, methods=["GET", "HEAD"]),
    Route("/api/v1/health", health.get, methods=["GET", "HEAD"]),
    Route("/api/v1/transactions/stream", transactions.stream),
    Route("/api/v1/transactions/list", transactions.list_transactions),
    Route("/api/v1/transactions/{transaction_hash}", transactions.get),
    Route("/api/v1/notes/{note_id}", notes.search),
    Route("/api/v1/channels/list", channels.list_channels),
    Route("/api/v1/channels/{channel_id}", channels.get_channel),
    Route("/api/v1/blocks/stream", blocks.stream),
    Route("/api/v1/blocks/list", blocks.list_blocks),
    Route("/api/v1/blocks/{block_hash}", blocks.get),
    # Catch-all for the single-page frontend; must stay last.
    Route("/{path:path}", spa),
]


class RootPathMiddleware:
    """Serve the app under a path prefix, e.g. "/web/explorer" behind a reverse proxy.

    Requests arrive with the prefix still on the path (the proxy does not strip
    it), so the prefix is stamped as the scope's root_path here rather than
    passed to uvicorn, which would expect it stripped. Routing ignores the
    prefix and the SPA reads it for its <base href>.
    """

    def __init__(self, app: ASGIApp, root_path: str) -> None:
        self.app = app
        self.root_path = root_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and self.root_path:
            scope["root_path"] = self.root_path
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: Starlette):
    settings: Settings = app.state.settings
    app.state.db = Database(settings.database_path)
    app.state.node_api = HttpNodeApi(settings)
    app.state.notifier = ChainNotifier()
    app.state.lib_slot = 0
    try:
        async with run_ingestion(app):
            yield
    finally:
        await app.state.node_api.aclose()
        app.state.db.close()


def create_app(settings: Settings) -> Starlette:
    app = Starlette(
        routes=ROUTES,
        lifespan=lifespan,
        exception_handlers={HTTPException: http_exception},
        middleware=[Middleware(RootPathMiddleware, root_path=settings.base_path)],
    )
    app.state.settings = settings
    return app
