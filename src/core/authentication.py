import base64
import dataclasses

import httpx


@dataclasses.dataclass
class Authentication:
    """Value of NBE_NODE_API_AUTH, e.g. "Basic dXNlcjpwYXNz"."""

    type: str
    credentials: str

    @classmethod
    def from_string(cls, string: str) -> "Authentication":
        auth_type, credentials = string.split(" ", 1)
        return cls(auth_type.lower(), credentials)

    def for_httpx(self) -> httpx.BasicAuth:
        if self.type == "basic":
            decoded = base64.b64decode(self.credentials).decode("utf-8")
            username, password = decoded.split(":", 1)
            return httpx.BasicAuth(username, password)
        raise NotImplementedError(f"Unsupported auth type: {self.type}")
