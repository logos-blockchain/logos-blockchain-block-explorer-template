from typing import List

from pydantic import Field

from core.models import NbeSerializer
from node.api.serializers.fields import BytesFromHex
from node.api.serializers.operation import MantleOpSerializerField


class TransactionSerializer(NbeSerializer):
    ops: List[MantleOpSerializerField]
    # Blake2b-256("MANTLE_TXHASH_V1" || canonical op encoding), computed by the
    # node. The explorer never derives it locally.
    hash: BytesFromHex = Field(description="Canonical transaction hash.")
