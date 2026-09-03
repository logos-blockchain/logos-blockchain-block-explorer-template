from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

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
    app = Starlette(routes=ROUTES, lifespan=lifespan, exception_handlers={HTTPException: http_exception})
    app.state.settings = settings
    return app
