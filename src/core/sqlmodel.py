from typing import Any, Generic, List, TypeVar

from pydantic import TypeAdapter
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON as SA_JSON, TypeDecorator

T = TypeVar("T")


class PydanticJsonColumn(TypeDecorator, Generic[T]):
    """
    Store/load a Pydantic v2 model (or list of models) in a JSON/JSONB column.

    Python -> DB: accepts Model | dict | list[Model] | list[dict],
      emits dict or list[dict] (what JSON columns expect).
    DB -> Python: returns Model or list[Model], preserving shape.
    """

    impl = SA_JSON
    cache_ok = True

    def __init__(self, model: type[T], *, many: bool = False) -> None:
        """
        The passed model must be a non-list type. To specify a list of models, pass `many=True`.
        """
        super().__init__()
        self.many = many
        self._ta = TypeAdapter(List[model] if many else model)

    # Use JSONB on Postgres, JSON elsewhere
    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(JSONB()) if dialect.name == "postgresql" else dialect.type_descriptor(SA_JSON())

    # Python -> DB (on INSERT/UPDATE)
    def process_bind_param(self, value: Any, _dialect) -> Any:
        if value is None:
            return [] if self.many else None
        return self._ta.dump_python(self._ta.validate_python(value), mode="json")

    # DB -> Python (on SELECT)
    def process_result_value(self, value: Any, _dialect):
        if value is None:
            return [] if self.many else None
        return self._ta.validate_python(value)
