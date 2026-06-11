from random import randint
from typing import Annotated, Any, List, Self, Union

from pydantic import BeforeValidator, Field

from core.models import NbeSerializer
from node.api.serializers.fields import BytesFromHex, BytesFromIntArray
from node.api.serializers.note import NoteSerializer
from utils.protocols import FromRandom
from utils.random import random_bytes

# Mantle op opcodes (new node release).
OPCODE_LEDGER = 0
OPCODE_CHANNEL_INSCRIBE = 17


class LedgerOpSerializer(NbeSerializer, FromRandom):
    """Mantle ledger op (opcode 0): consumes input notes and produces outputs."""

    inputs: List[BytesFromHex] = Field(description="Input note IDs (Fr).")
    outputs: List[NoteSerializer]

    @classmethod
    def from_random(cls) -> Self:
        n_inputs = 0 if randint(0, 1) <= 0.5 else randint(1, 5)
        n_outputs = 0 if randint(0, 1) <= 0.5 else randint(1, 5)
        return cls.model_validate(
            {
                "inputs": [random_bytes(32).hex() for _ in range(n_inputs)],
                "outputs": [NoteSerializer.from_random() for _ in range(n_outputs)],
            }
        )


class ChannelInscribeOpSerializer(NbeSerializer, FromRandom):
    """Channel inscribe op (opcode 17): writes an inscription to a channel."""

    channel_id: BytesFromHex = Field(description="Channel ID in hex format.")
    inscription: BytesFromIntArray = Field(description="Inscription bytes (int array).")
    parent: BytesFromHex = Field(description="Parent inscription hash in hex format.")
    signer: BytesFromHex = Field(description="Signer public key in hex format.")

    @classmethod
    def from_random(cls) -> Self:
        return cls.model_validate(
            {
                "channel_id": random_bytes(32).hex(),
                "inscription": list(random_bytes(32)),
                "parent": random_bytes(32).hex(),
                "signer": random_bytes(32).hex(),
            }
        )

class UnknownOpSerializer(NbeSerializer):
    """Fallback serializer for unrecognized opcodes."""
    opcode: int
    payload: dict[str, Any] = Field(default_factory=dict)


OPCODE_TO_SERIALIZER: dict[int, type] = {
    OPCODE_LEDGER: LedgerOpSerializer,
    OPCODE_CHANNEL_INSCRIBE: ChannelInscribeOpSerializer,
}


def _parse_mantle_op(data: Any) -> Any:
    if isinstance(data, (LedgerOpSerializer, ChannelInscribeOpSerializer, UnknownOpSerializer)):
        return data
    if isinstance(data, dict) and "opcode" in data:
        opcode = data["opcode"]
        serializer_class = OPCODE_TO_SERIALIZER.get(opcode)
        if serializer_class is None:
            return UnknownOpSerializer(opcode=opcode, payload=data.get("payload", {}))
        return serializer_class.model_validate(data["payload"])
    raise ValueError(f"Cannot parse mantle op from {type(data).__name__}.")


MantleOpSerializerVariants = Union[LedgerOpSerializer, ChannelInscribeOpSerializer, UnknownOpSerializer]
MantleOpSerializerField = Annotated[MantleOpSerializerVariants, BeforeValidator(_parse_mantle_op)]
