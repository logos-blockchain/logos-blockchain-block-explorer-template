import base64
import dataclasses

import httpx


@dataclasses.dataclass
class Authentication:
    _raw: str
    type: str
    credentials: str

    @classmethod
    def from_string(cls, string: str) -> "Authentication":
        (auth_type, credentials) = string.split(" ", 1)
        return cls(string, auth_type.lower(), credentials)

    def for_requests(self) -> str:
        return self._raw

    def for_httpx(self) -> httpx.BasicAuth:
        if self.type == "basic":
            decoded = base64.b64decode(self.credentials).decode("utf-8")
            (username, password) = decoded.split(":", 1)
            return httpx.BasicAuth(username, password)
        raise NotImplementedError
