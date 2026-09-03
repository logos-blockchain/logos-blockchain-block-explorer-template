import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from constants import DIR_REPO

ENV_FILEPATH = DIR_REPO.joinpath(".env")


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
    """Value of NBE_NODE_API_AUTH, e.g. "Basic dXNlcjpwYXNz"."""
    scheme, _, credentials = value.strip().partition(" ")
    if scheme.lower() != "basic" or not credentials:
        raise ValueError(f"Invalid NBE_NODE_API_AUTH: {value!r} (expected 'Basic <base64 user:password>')")
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
        env = os.environ
        auth = env.get("NBE_NODE_API_AUTH")
        return cls(
            host=env.get("NBE_HOST", cls.host),
            port=int(env.get("NBE_PORT", cls.port)),
            base_path=env.get("NBE_BASE_PATH", "").strip().rstrip("/"),
            node_api_host=env.get("NBE_NODE_API_HOST", cls.node_api_host),
            node_api_port=int(env.get("NBE_NODE_API_PORT", cls.node_api_port)),
            node_api_protocol=env.get("NBE_NODE_API_PROTOCOL", cls.node_api_protocol),
            node_api_timeout=int(env.get("NBE_NODE_API_TIMEOUT", cls.node_api_timeout)),
            node_api_auth=parse_basic_auth(auth) if auth else None,
            database_path=env.get("NBE_DATABASE_PATH", cls.database_path),
        )
