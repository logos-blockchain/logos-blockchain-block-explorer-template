from typing import Any, Literal, Optional

from core.models import LbeSchema
from core.types import HexBytes


class LbeSignature(LbeSchema):
    type: str


class Ed25519Signature(LbeSignature):
    type: Literal["Ed25519"] = "Ed25519"
    signature: HexBytes


class ZkSignature(LbeSignature):
    type: Literal["Zk"] = "Zk"
    signature: HexBytes


class ZkAndEd25519Signature(LbeSignature):
    type: Literal["ZkAndEd25519"] = "ZkAndEd25519"
    zk_signature: HexBytes
    ed25519_signature: HexBytes


class PoCSignature(LbeSignature):
    type: Literal["PoC"] = "PoC"
    proof: HexBytes


class IndexedSignature(LbeSchema):
    signature: HexBytes
    channel_key_index: int


class ChannelMultiSignature(LbeSignature):
    type: Literal["ChannelMultiSig"] = "ChannelMultiSig"
    signatures: list[IndexedSignature]


class NoneProof(LbeSignature):
    """Ops that require no proof (e.g. ClaimPowReward)."""

    type: Literal["None"] = "None"


class UnknownSignature(LbeSignature):
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
