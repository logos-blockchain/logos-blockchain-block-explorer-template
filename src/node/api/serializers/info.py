from pydantic import BaseModel


class InfoSerializer(BaseModel):
    lib: str  # Last Irreversible Block hash
    lib_slot: int = 0  # Slot of the LIB; the node prunes non-canonical blocks below it
    tip: str  # Current tip block hash
    slot: int  # Current slot
    height: int  # Current height
    mode: str  # Node mode (e.g., "Online")
