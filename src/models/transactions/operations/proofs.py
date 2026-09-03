from typing import Any, Literal, Optional

from core.models import NbeSchema
from core.types import HexBytes


class NbeSignature(NbeSchema):
    type: str


class Ed25519Signature(NbeSignature):
    type: Literal["Ed25519"] = "Ed25519"
    signature: HexBytes


class ZkSignature(NbeSignature):
    type: Literal["Zk"] = "Zk"
    signature: HexBytes


class ZkAndEd25519Signature(NbeSignature):
    type: Literal["ZkAndEd25519"] = "ZkAndEd25519"
    zk_signature: HexBytes
    ed25519_signature: HexBytes


class PoCSignature(NbeSignature):
    type: Literal["PoC"] = "PoC"
    proof: HexBytes


class IndexedSignature(NbeSchema):
    signature: HexBytes
    channel_key_index: int


class ChannelMultiSignature(NbeSignature):
    type: Literal["ChannelMultiSig"] = "ChannelMultiSig"
    signatures: list[IndexedSignature]


class NoneProof(NbeSignature):
    """Ops that require no proof (e.g. ClaimPowReward)."""

    type: Literal["None"] = "None"


class UnknownSignature(NbeSignature):
    """Fallback for proof variants without a typed model (same approach as #19).

    `raw` holds the value verbatim — it covers unit variants like "NoProof"
    (which carry no signature bytes) as well as future tagged variants.
    """

    type: Literal["Unknown"] = "Unknown"
    raw: Optional[Any] = None


OperationProof = (
    Ed25519Signature
    | ZkSignature
    | ZkAndEd25519Signature
    | PoCSignature
    | ChannelMultiSignature
    | NoneProof
    | UnknownSignature
)
