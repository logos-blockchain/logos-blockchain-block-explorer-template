from typing import Annotated, Union

from pydantic import BeforeValidator, PlainSerializer, ValidationError


def bytes_from_intarray(data: list[int]) -> bytes:
    if not isinstance(data, list):
        raise ValueError(f"Unsupported data type for bytes deserialization. Expected list, got {type(data).__name__}.")
    elif not all(isinstance(item, int) for item in data):
        raise ValueError("List items must be integers.")
    else:
        return bytes(data)


def bytes_from_hex(data: str) -> bytes:
    if not isinstance(data, str):
        raise ValueError(
            f"Unsupported data type for bytes deserialization. Expected string, got {type(data).__name__}."
        )
    return bytes.fromhex(data)


def bytes_from_int(data: int) -> bytes:
    if not isinstance(data, int):
        raise ValueError(
            f"Unsupported data type for bytes deserialization. Expected integer, got {type(data).__name__}."
        )
    return data.to_bytes((data.bit_length() + 7) // 8)  # TODO: Ensure endianness is correct.


def bytes_from_hex_or_intarray(data: Union[str, list[int]]) -> bytes:
    """Accepts either hex string or int array and converts to bytes."""
    if isinstance(data, str):
        return bytes.fromhex(data)
    elif isinstance(data, list):
        if not all(isinstance(item, int) for item in data):
            raise ValueError("List items must be integers.")
        return bytes(data)
    else:
        raise ValueError(
            f"Unsupported data type for bytes deserialization. Expected string or list, got {type(data).__name__}."
        )


def bytes_into_hex(data: bytes) -> str:
    return data.hex()


BytesFromIntArray = Annotated[bytes, BeforeValidator(bytes_from_intarray), PlainSerializer(bytes_into_hex)]
BytesFromHex = Annotated[bytes, BeforeValidator(bytes_from_hex), PlainSerializer(bytes_into_hex)]
BytesFromInt = Annotated[bytes, BeforeValidator(bytes_from_int), PlainSerializer(bytes_into_hex)]
BytesFlexible = Annotated[bytes, BeforeValidator(bytes_from_hex_or_intarray), PlainSerializer(bytes_into_hex)]