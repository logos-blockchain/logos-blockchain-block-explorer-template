from enum import Enum
from typing import Any, List, Literal, Optional

from core.models import NbeSchema
from core.types import HexBytes
from models.transactions.notes import Note


class ContentType(Enum):
    LEDGER_TRANSFER = "LedgerTransfer"
    CHANNEL_INSCRIBE = "ChannelInscribe"
    CHANNEL_BLOB = "ChannelBlob"
    CHANNEL_SET_KEYS = "ChannelSetKeys"
    CHANNEL_CONFIG = "ChannelConfig"
    CHANNEL_DEPOSIT = "ChannelDeposit"
    CHANNEL_WITHDRAW = "ChannelWithdraw"
    CHANNEL_TRANSFER = "ChannelTransfer"
    SDP_DECLARE = "SDPDeclare"
    SDP_WITHDRAW = "SDPWithdraw"
    SDP_ACTIVE = "SDPActive"
    LEADER_CLAIM = "LeaderClaim"


class NbeContent(NbeSchema):
    type: str


class LedgerTransfer(NbeContent):
    type: Literal["LedgerTransfer"] = "LedgerTransfer"
    inputs: List[HexBytes]
    outputs: List[Note]


class ChannelInscribe(NbeContent):
    type: Literal["ChannelInscribe"] = "ChannelInscribe"
    channel_id: HexBytes
    inscription: HexBytes
    parent: HexBytes
    signer: HexBytes


class ChannelBlob(NbeContent):
    type: Literal["ChannelBlob"] = "ChannelBlob"
    channel: HexBytes
    blob: HexBytes
    blob_size: int
    da_storage_gas_price: int
    parent: HexBytes
    signer: HexBytes


class ChannelSetKeys(NbeContent):
    """Legacy pre-0.2.x op kept so old DB rows still deserialize."""

    type: Literal["ChannelSetKeys"] = "ChannelSetKeys"
    channel: HexBytes
    # HexBytes (not plain bytes): content is stored as JSON in the DB, and raw
    # bytes break its utf-8 encoding for arbitrary key material.
    keys: List[HexBytes]


class ChannelConfig(NbeContent):
    type: Literal["ChannelConfig"] = "ChannelConfig"
    channel: HexBytes
    keys: List[HexBytes]
    posting_timeframe: int
    posting_timeout: int
    configuration_threshold: int
    transfer_threshold: int


class ChannelDeposit(NbeContent):
    type: Literal["ChannelDeposit"] = "ChannelDeposit"
    channel_id: HexBytes
    inputs: List[HexBytes]
    metadata: HexBytes


class ChannelWithdraw(NbeContent):
    type: Literal["ChannelWithdraw"] = "ChannelWithdraw"
    channel_id: HexBytes
    inputs: List[HexBytes]


class ChannelTransfer(NbeContent):
    type: Literal["ChannelTransfer"] = "ChannelTransfer"
    channel_id: HexBytes
    inputs: List[HexBytes]
    outputs: List[Note]


class SDPDeclareServiceType(Enum):
    BN = "BN"
    DA = "DA"


class SDPDeclare(NbeContent):
    type: Literal["SDPDeclare"] = "SDPDeclare"
    service_type: SDPDeclareServiceType
    locators: List[str]
    provider_id: HexBytes
    zk_id: HexBytes
    locked_note_id: HexBytes


class SDPWithdraw(NbeContent):
    type: Literal["SDPWithdraw"] = "SDPWithdraw"
    declaration_id: HexBytes
    nonce: int
    locked_note_id: HexBytes


class SDPActive(NbeContent):
    type: Literal["SDPActive"] = "SDPActive"
    declaration_id: HexBytes
    nonce: int
    metadata: Optional[Any] = None


class LeaderClaim(NbeContent):
    type: Literal["LeaderClaim"] = "LeaderClaim"
    rewards_root: HexBytes
    voucher_nullifier: HexBytes
    pk: HexBytes


class UnknownOp(NbeContent):
    """Fallback for mantle ops without a typed model (same approach as #19).

    Preserves the opcode and raw payload verbatim so new node op types never
    break block ingestion; typed support can be added later.
    """

    type: Literal["UnknownOp"] = "UnknownOp"
    opcode: int
    raw_payload: Optional[Any] = None


OperationContent = (
    LedgerTransfer
    | ChannelInscribe
    | ChannelBlob
    | ChannelSetKeys
    | ChannelConfig
    | ChannelDeposit
    | ChannelWithdraw
    | ChannelTransfer
    | SDPDeclare
    | SDPWithdraw
    | SDPActive
    | LeaderClaim
    | UnknownOp
)
