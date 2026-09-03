import base64
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from constants import DIR_REPO

ENV_FILEPATH = DIR_REPO.joinpath(".env")

logger = logging.getLogger(__name__)


def env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    """An LBE_* variable, falling back to its NBE_* predecessor.

    Deployments still set the NBE_* names (the project was the Nomos Block
    Explorer); the fallback goes once they have moved to LBE_*.
    """
    value = os.environ.get(f"LBE_{name}")
    if value is None:
        legacy = f"NBE_{name}"
        value = os.environ.get(legacy)
        if value is not None:
            logger.warning(f"{legacy} is deprecated; set LBE_{name} instead")
    return default if value is None else value


def load_dotenv(path: Path = ENV_FILEPATH) -> None:
    """Load KEY=VALUE lines from a .env file into the environment. Variables already set win."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def parse_basic_auth(value: str) -> httpx.BasicAuth:
    """Value of LBE_NODE_API_AUTH, e.g. "Basic dXNlcjpwYXNz"."""
    scheme, _, credentials = value.strip().partition(" ")
    if scheme.lower() != "basic" or not credentials:
        raise ValueError(f"Invalid LBE_NODE_API_AUTH: {value!r} (expected 'Basic <base64 user:password>')")
    username, _, password = base64.b64decode(credentials).decode("utf-8").partition(":")
    return httpx.BasicAuth(username, password)


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 8000
    # Path prefix the explorer is served under behind a reverse proxy, e.g. "/explorer".
    base_path: str = ""

    node_api_host: str = "127.0.0.1"
    node_api_port: int = 8080
    node_api_protocol: str = "http"
    node_api_timeout: int = 60
    node_api_auth: Optional[httpx.BasicAuth] = None

    database_path: str = str(DIR_REPO.joinpath("sqlite.db"))

    @classmethod
    def from_env(cls) -> "Settings":
        auth = env_var("NODE_API_AUTH")
        return cls(
            host=env_var("HOST", cls.host),
            port=int(env_var("PORT", str(cls.port))),
            base_path=env_var("BASE_PATH", "").strip().rstrip("/"),
            node_api_host=env_var("NODE_API_HOST", cls.node_api_host),
            node_api_port=int(env_var("NODE_API_PORT", str(cls.node_api_port))),
            node_api_protocol=env_var("NODE_API_PROTOCOL", cls.node_api_protocol),
            node_api_timeout=int(env_var("NODE_API_TIMEOUT", str(cls.node_api_timeout))),
            node_api_auth=parse_basic_auth(auth) if auth else None,
            database_path=cls._database_path(),
        )

    @classmethod
    def _database_path(cls) -> str:
        path = env_var("DATABASE_PATH")
        if path is not None:
            return path
        # Deployments still pass the SQLAlchemy-style URL the explorer used to take.
        url = os.environ.get("NBE_DATABASE_URL")
        if url is not None:
            logger.warning("NBE_DATABASE_URL is deprecated; set LBE_DATABASE_PATH to the database file path instead")
            if not url.startswith("sqlite:///"):
                raise ValueError(f"Unsupported NBE_DATABASE_URL: {url!r} (only sqlite:/// URLs were ever supported)")
            return url.removeprefix("sqlite:///")
        return cls.database_path
