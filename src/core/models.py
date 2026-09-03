from pydantic import BaseModel


class NbeSchema(BaseModel):
    """Base for stored models, API schemas and JSON-column payloads."""


class NbeSerializer(NbeSchema):
    """Base for node wire-format serializers."""
