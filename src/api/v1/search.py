from http.client import BAD_REQUEST, NOT_FOUND
from typing import TYPE_CHECKING

from fastapi import Path
from starlette.responses import JSONResponse, Response

from core.api import NBERequest
from core.types import dehexify

if TYPE_CHECKING:
    from core.app import NBE


async def search(request: NBERequest, hash: str = Path(...)) -> Response:
    """
    Search for a block or transaction by hash.

    Returns:
        - 200 with {"type": "block"|"transaction", "id": int} if found
        - 404 if not found
        - 400 if hash is invalid
    """
    if not hash:
        return Response(status_code=BAD_REQUEST)

    try:
        if hash.startswith("0x"):
            hash = hash[2:]
        normalized_hash = dehexify(hash)
    except ValueError:
        return Response(status_code=BAD_REQUEST)

    result = await request.app.state.search_repository.search_by_hash(normalized_hash)

    if result is None:
        return Response(status_code=NOT_FOUND)

    result_type, result_id = result
    return JSONResponse({"type": result_type, "id": result_id})
