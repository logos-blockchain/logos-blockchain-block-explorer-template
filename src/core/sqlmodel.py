import logging
from typing import Any, Generic, List, Literal, TypeVar

from pydantic import TypeAdapter
from pydantic.config import ExtraValues
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON as SA_JSON, TypeDecorator

T = TypeVar("T")

logger = logging.getLogger(__name__)


class _TypeAdapter(TypeAdapter):  # type: ignore[misc]
    def validate_json(
        self,
        data: str | bytes | bytearray,
        /,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        context: Any | None = None,
        experimental_allow_partial: bool | Literal["off", "on", "trailing-strings"] = False,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> T:
        logger.warning("""
            Method `TypeAdapter::validate_json` is known to not deserialize JSON columns correctly under certain conditions.
            For more context read `NbeModel::model_validate_json`'s pydoc.
            """)
        return super().validate_json(
            data,
            strict=strict,
            extra=extra,
            context=context,
            experimental_allow_partial=experimental_allow_partial,
            by_alias=by_alias,
            by_name=by_name,
        )


class PydanticJsonColumn(TypeDecorator, Generic[T]):
    """
    Store/load a Pydantic v2 model (or list of models) in a JSON/JSONB column.

    Python -> DB: accepts Model | dict | list[Model] | list[dict] | JSON str/bytes,
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
        self._ta = _TypeAdapter(List[model] if many else model)

    # Use JSONB on Postgres, JSON elsewhere
    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(JSONB()) if dialect.name == "postgresql" else dialect.type_descriptor(SA_JSON())

    # Python -> DB (on INSERT/UPDATE)
    def process_bind_param(self, value: Any, _dialect) -> Any:
        if value is None:
            return [] if self.many else None

        # If given JSON text/bytes, validate from JSON; else from Python
        if isinstance(value, (str, bytes, bytearray)):
            model_value = self._ta.validate_json(value.decode() if not isinstance(value, str) else value)
        else:
            model_value = self._ta.validate_python(value)

        # Dump to plain Python (dict/list) for the JSON column
        plain = self._ta.dump_python(model_value, mode="json")
        return plain

    # DB -> Python (on SELECT)
    def process_result_value(self, value: Any, _dialect):
        if value is None:
            return [] if self.many else None
        return self._ta.validate_python(value)
