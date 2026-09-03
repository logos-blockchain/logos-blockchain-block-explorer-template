from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer


def bytes_from_hex(data: str) -> bytes:
    if not isinstance(data, str):
        raise ValueError(f"Expected a hex string, got {type(data).__name__}.")
    return bytes.fromhex(data)


def bytes_from_hex_or_intarray(data: str | list[int]) -> bytes:
    """Byte fields the node may emit either as hex or as a JSON int array.

    serde emits plain `[u8; N]` fields (e.g. ClaimPowReward.block_hash) as int
    arrays, while newtype-wrapped hashes and keys arrive as hex strings.
    """
    if isinstance(data, str):
        return bytes_from_hex(data)
    if isinstance(data, list) and all(isinstance(item, int) for item in data):
        return bytes(data)
    raise ValueError(f"Expected a hex string or int array, got {type(data).__name__}.")


def bytes_into_hex(data: bytes) -> str:
    return data.hex()


BytesFromHex = Annotated[bytes, BeforeValidator(bytes_from_hex), PlainSerializer(bytes_into_hex)]
BytesFromHexOrIntArray = Annotated[bytes, BeforeValidator(bytes_from_hex_or_intarray), PlainSerializer(bytes_into_hex)]
