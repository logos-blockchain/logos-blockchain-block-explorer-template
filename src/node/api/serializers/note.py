from pydantic import Field

from core.models import LbeSerializer
from models.transactions.notes import Note
from node.api.serializers.fields import BytesFromHex


class NoteSerializer(LbeSerializer):
    value: int = Field(description="Integer in u64 format.")
    public_key: BytesFromHex = Field(alias="pk", description="Fr integer.")

    def into_note(self) -> Note:
        return Note.model_validate({"value": self.value, "public_key": self.public_key})
