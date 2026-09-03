from fastapi import APIRouter

from api.router import create_api_router
from frontend import create_frontend_router


def create_router() -> APIRouter:
    router = APIRouter()
    router.include_router(create_api_router(), prefix="/api")
    router.include_router(create_frontend_router())  # Needs to go last since it contains a catch-all route
    return router
