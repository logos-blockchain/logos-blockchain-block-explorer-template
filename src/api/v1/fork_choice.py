from http.client import NOT_FOUND

from starlette.responses import JSONResponse, Response

from core.api import NBERequest


async def get(request: NBERequest) -> Response:
    fork = await request.app.state.block_repository.get_fork_choice()
    if fork is None:
        return Response(status_code=NOT_FOUND)
    return JSONResponse({"fork": fork})
