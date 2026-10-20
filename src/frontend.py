from http.client import NOT_FOUND

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from constants import DIR_REPO

STATIC_DIR = DIR_REPO.joinpath("static")
# The app's own modules; the vendored ones are preloaded by index.html itself.
APP_MODULES = sorted(
    path.relative_to(STATIC_DIR.parent).as_posix()
    for path in STATIC_DIR.rglob("*.js")
    if STATIC_DIR.joinpath("vendor") not in path.parents
)
INDEX_TEMPLATE = (
    STATIC_DIR.joinpath("index.html")
    .read_text()
    .replace(
        "__MODULE_PRELOADS__",
        "\n        ".join(f'<link rel="modulepreload" href="{module}" />' for module in APP_MODULES),
    )
)

static_files = StaticFiles(directory=STATIC_DIR)


async def spa(request: Request) -> HTMLResponse:
    if request.path_params["path"].startswith(("api", "static")):
        # Not a page: an API route or asset that does not exist.
        raise HTTPException(NOT_FOUND)
    root_path = request.scope.get("root_path", "")
    base_path = root_path.rstrip("/") + "/"
    return HTMLResponse(INDEX_TEMPLATE.replace("__BASE_PATH__", base_path))
