from http.client import NOT_FOUND

from starlette.responses import JSONResponse, Response

from core.api import NBERequest


async def get(request: NBERequest) -> Response:
    fork = await request.app.state.block_repository.get_fork_choice()
    return fork.map(lambda f: JSONResponse({"fork": f})).unwrap_or_else(lambda: Response(status_code=NOT_FOUND))
