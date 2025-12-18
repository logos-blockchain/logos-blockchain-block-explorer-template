from constants import DIR_REPO

STATIC_DIR = DIR_REPO.joinpath("static")

from .router import create_frontend_router
