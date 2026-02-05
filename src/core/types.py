from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, PlainSerializer


def hexify(data: bytes) -> str:
    return data.hex()


def dehexify(data: str) -> bytes:
    return bytes.fromhex(data)


def validate_hex_bytes(data: str | bytes) -> bytes:
    if isinstance(data, bytes):
        return data
    return bytes.fromhex(data)


HexBytes = Annotated[
    bytes,
    BeforeValidator(validate_hex_bytes),
    PlainSerializer(hexify, return_type=str, when_used="json"),
]
