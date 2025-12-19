from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, PlainSerializer


def hexify(data: bytes) -> str:
    return data.hex()


def dehexify(data: str) -> bytes:
    return bytes.fromhex(data)


HexBytes = Annotated[
    bytes,
    PlainSerializer(hexify, return_type=str, when_used="json"),
]
