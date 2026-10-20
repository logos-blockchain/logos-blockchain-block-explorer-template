from pydantic import BaseModel


class LbeSchema(BaseModel):
    """Base for stored models, API schemas and JSON-column payloads."""


class LbeSerializer(LbeSchema):
    """Base for node wire-format serializers."""
