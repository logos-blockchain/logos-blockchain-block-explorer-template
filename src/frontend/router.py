from http.client import NOT_FOUND

from fastapi import APIRouter, HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse

from . import STATIC_DIR

INDEX_FILE = STATIC_DIR.joinpath("index.html")
INDEX_TEMPLATE = INDEX_FILE.read_text()


def spa(request: Request, path: str) -> HTMLResponse:
    if path.startswith(("api", "static")):
        # Not a page: an API route or asset that does not exist.
        raise HTTPException(NOT_FOUND)
    root_path = request.scope.get("root_path", "")
    base_path = root_path.rstrip("/") + "/"
    html = INDEX_TEMPLATE.replace("__BASE_PATH__", base_path)
    return HTMLResponse(html)


def create_frontend_router() -> APIRouter:
    router = APIRouter()
    router.get("/{path:path}", include_in_schema=False)(spa)
    return router
