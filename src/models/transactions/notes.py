from core.models import LbeSchema
from core.types import HexBytes


class Note(LbeSchema):
    value: int
    public_key: HexBytes
