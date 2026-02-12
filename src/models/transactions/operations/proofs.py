from enum import Enum
from typing import Literal

from core.models import NbeSchema
from core.types import HexBytes


class SignatureType(Enum):
    ED25519 = "Ed25519"
    ZK = "Zk"
    ZK_AND_ED25519 = "ZkAndEd25519"


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


OperationProof = Ed25519Signature | ZkSignature | ZkAndEd25519Signature
