from typing import Optional

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


class NbeSchema(BaseModel):
    """Base for API schemas and JSON-column payloads."""


class NbeSerializer(NbeSchema):
    """Base for node wire-format serializers."""


class NbeModel(SQLModel):
    """Base for database tables."""


class IdNbeModel(NbeModel):
    id: Optional[int] = Field(default=None, primary_key=True)
