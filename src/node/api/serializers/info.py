from pydantic import BaseModel


class InfoSerializer(BaseModel):
    lib: str  # Last Irreversible Block hash
    tip: str  # Current tip block hash
    slot: int  # Current slot
    height: int  # Current height
    mode: str  # Node mode (e.g., "Online")
