from typing import List, Optional

from pydantic import Field

from core.models import NbeSerializer
from node.api.serializers.fields import BytesFromHex
from node.api.serializers.operation import MantleOpSerializerField


class TransactionSerializer(NbeSerializer):
    ops: List[MantleOpSerializerField]
    # Newer nodes include the canonical tx hash in mantle_tx; older ones don't.
    hash: Optional[BytesFromHex] = Field(default=None, description="Canonical tx hash (newer nodes only).")
    # Gas prices were dropped from mantle_tx on newer nodes; default to 0 there.
    execution_gas_price: int = Field(default=0, description="Integer in u64 format.")
    storage_gas_price: int = Field(default=0, description="Integer in u64 format.")
