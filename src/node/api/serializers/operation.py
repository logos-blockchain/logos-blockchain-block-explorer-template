import logging
from typing import Annotated, Any, List, Optional, Self, Union

from pydantic import AliasChoices, BeforeValidator, Field

from core.models import NbeSerializer
from models.transactions.operations.contents import SDPDeclareServiceType
from node.api.serializers.fields import BytesFromHex, BytesFromHexOrIntArray
from node.api.serializers.note import NoteSerializer

logger = logging.getLogger(__name__)

# Mantle op opcodes (node 0.3.0-rc.2: core/src/mantle/ops/mod.rs).
OPCODE_TRANSFER = 0  # 0x00
OPCODE_CHANNEL_CONFIG = 16  # 0x10
OPCODE_CHANNEL_INSCRIBE = 17  # 0x11
OPCODE_CHANNEL_DEPOSIT = 18  # 0x12
OPCODE_CHANNEL_WITHDRAW = 19  # 0x13
OPCODE_CHANNEL_TRANSFER = 20  # 0x14
OPCODE_SDP_DECLARE = 32  # 0x20
OPCODE_SDP_WITHDRAW = 33  # 0x21
OPCODE_SDP_ACTIVE = 34  # 0x22
OPCODE_LEADER_CLAIM = 48  # 0x30
OPCODE_CLAIM_POW_REWARD = 64  # 0x40


class LedgerOpSerializer(NbeSerializer):
    """Mantle ledger op (opcode 0): consumes input notes and produces outputs."""

    inputs: List[BytesFromHex] = Field(description="Input note IDs (Fr).")
    outputs: List[NoteSerializer]


class ChannelConfigOpSerializer(NbeSerializer):
    """Channel config op (opcode 16): configures a channel's keys, timeframes and thresholds.

    Replaces the pre-0.2.x set-keys op.
    """

    channel: BytesFromHexOrIntArray = Field(description="Channel ID.")
    # Added in node 0.3.0: the config-chain parent (MsgId::root() for a first config).
    parent: Optional[BytesFromHexOrIntArray] = Field(default=None, description="Parent config message id.")
    keys: List[BytesFromHexOrIntArray] = Field(description="Channel signing public keys.")
    posting_timeframe: int = Field(description="Posting timeframe in slots (u32).")
    posting_timeout: int = Field(description="Posting timeout in slots (u32).")
    configuration_threshold: int = Field(description="Signatures required to reconfigure (u16).")
    transfer_threshold: int = Field(description="Signatures required to transfer/withdraw (u16).")


class ChannelDepositOpSerializer(NbeSerializer):
    """Channel deposit op (opcode 18): locks input notes into a channel."""

    channel_id: BytesFromHexOrIntArray = Field(description="Channel ID.")
    inputs: List[BytesFromHex] = Field(description="Input note IDs (Fr).")
    metadata: BytesFromHexOrIntArray = Field(description="Deposit metadata bytes.")


class ChannelWithdrawOpSerializer(NbeSerializer):
    """Channel withdraw op (opcode 19): withdraws channel notes."""

    channel_id: BytesFromHexOrIntArray = Field(description="Channel ID.")
    inputs: List[BytesFromHex] = Field(description="Input note IDs (Fr).")


class ChannelTransferOpSerializer(NbeSerializer):
    """Channel transfer op (opcode 20): transfers channel notes to new outputs."""

    channel_id: BytesFromHexOrIntArray = Field(description="Channel ID.")
    inputs: List[BytesFromHex] = Field(description="Input note IDs (Fr).")
    outputs: List[NoteSerializer]


class ChannelInscribeOpSerializer(NbeSerializer):
    """Channel inscribe op (opcode 17): writes an inscription to a channel."""

    channel_id: BytesFromHex = Field(description="Channel ID in hex format.")
    inscription: BytesFromHexOrIntArray = Field(
        description="Inscription bytes (int array on older nodes, hex string on newer ones)."
    )
    parent: BytesFromHex = Field(description="Parent inscription hash in hex format.")
    signer: BytesFromHex = Field(description="Signer public key in hex format.")


class SDPDeclareOpSerializer(NbeSerializer):
    """SDP declare op (opcode 32): registers a service provider."""

    service_type: SDPDeclareServiceType
    locators: List[str] = Field(description="Multiaddr strings, e.g. /ip4/.../udp/.../quic-v1.")
    provider_id: BytesFromHex = Field(description="Provider ID in hex format.")
    zk_id: BytesFromHex = Field(description="ZK ID in hex format.")
    # Node 0.3.0 renamed locked_note_id -> service_note_id.
    service_note_id: BytesFromHex = Field(
        validation_alias=AliasChoices("service_note_id", "locked_note_id"),
        description="Service (stake) note ID in hex format.",
    )


class SDPActiveOpSerializer(NbeSerializer):
    """SDP active op (opcode 34): proves a declared provider is online."""

    declaration_id: BytesFromHex = Field(description="Declaration ID in hex format.")
    nonce: int = Field(description="Activity nonce in u64 format.")
    metadata: Optional[Any] = Field(
        default=None,
        description="Service-specific metadata (e.g. Blend session/proofs). Stored verbatim.",
    )


class SDPWithdrawOpSerializer(NbeSerializer):
    """SDP withdraw op (opcode 33): withdraws a provider's locked stake."""

    declaration_id: BytesFromHex = Field(description="Declaration ID in hex format.")
    nonce: int = Field(description="Nonce in u64 format.")
    # Node 0.3.0 renamed locked_note_id -> service_note_id.
    service_note_id: BytesFromHex = Field(
        validation_alias=AliasChoices("service_note_id", "locked_note_id"),
        description="Service (stake) note ID in hex format.",
    )


class LeaderClaimOpSerializer(NbeSerializer):
    """Leader claim op (opcode 48): claims a leader reward voucher."""

    rewards_root: BytesFromHex = Field(description="Rewards merkle root (Fr).")
    voucher_nullifier: BytesFromHex = Field(description="Voucher nullifier (Fr).")
    pk: BytesFromHex = Field(description="Reward recipient ZK public key (Fr).")


class ClaimPowRewardOpSerializer(NbeSerializer):
    """Claim PoW reward op (opcode 64, node 0.3.0+): redeems a mined puzzle ticket.

    Carries no proof (OpProof::None). `block_hash` is a plain [u8; 32] on the
    node, which serde emits as an int array; the Fr fields arrive as hex.
    """

    epoch_nonce: BytesFromHexOrIntArray = Field(description="Epoch nonce the ticket was mined against (Fr).")
    block_hash: BytesFromHexOrIntArray = Field(description="Hash of the block the ticket was mined on.")
    public_key: BytesFromHexOrIntArray = Field(description="Reward recipient ZK public key (Fr).")


class UnknownOpSerializer(NbeSerializer):
    """Fallback for opcodes without a typed serializer.

    Preserves the opcode and raw payload verbatim so unknown (e.g. newly
    introduced) op types never break block ingestion.
    """

    opcode: int
    payload: Optional[Any] = None


OPCODE_TO_SERIALIZER: dict[int, type] = {
    OPCODE_TRANSFER: LedgerOpSerializer,
    OPCODE_CHANNEL_CONFIG: ChannelConfigOpSerializer,
    OPCODE_CHANNEL_INSCRIBE: ChannelInscribeOpSerializer,
    OPCODE_CHANNEL_DEPOSIT: ChannelDepositOpSerializer,
    OPCODE_CHANNEL_WITHDRAW: ChannelWithdrawOpSerializer,
    OPCODE_CHANNEL_TRANSFER: ChannelTransferOpSerializer,
    OPCODE_SDP_DECLARE: SDPDeclareOpSerializer,
    OPCODE_SDP_WITHDRAW: SDPWithdrawOpSerializer,
    OPCODE_SDP_ACTIVE: SDPActiveOpSerializer,
    OPCODE_LEADER_CLAIM: LeaderClaimOpSerializer,
    OPCODE_CLAIM_POW_REWARD: ClaimPowRewardOpSerializer,
}


MantleOpSerializerVariants = Union[
    LedgerOpSerializer,
    ChannelConfigOpSerializer,
    ChannelInscribeOpSerializer,
    ChannelDepositOpSerializer,
    ChannelWithdrawOpSerializer,
    ChannelTransferOpSerializer,
    SDPDeclareOpSerializer,
    SDPWithdrawOpSerializer,
    SDPActiveOpSerializer,
    LeaderClaimOpSerializer,
    ClaimPowRewardOpSerializer,
    UnknownOpSerializer,
]
_MANTLE_OP_SERIALIZER_CLASSES = tuple(OPCODE_TO_SERIALIZER.values()) + (UnknownOpSerializer,)


def _parse_mantle_op(data: Any) -> MantleOpSerializerVariants:
    if isinstance(data, _MANTLE_OP_SERIALIZER_CLASSES):
        return data
    if isinstance(data, dict) and "opcode" in data:
        opcode = data["opcode"]
        serializer_class = OPCODE_TO_SERIALIZER.get(opcode)
        if serializer_class is None:
            logger.warning(f"No typed serializer for mantle op opcode {opcode}; storing it verbatim.")
            return UnknownOpSerializer.model_validate(data)
        try:
            return serializer_class.model_validate(data["payload"])
        except Exception:
            logger.warning(
                f"Payload for mantle op opcode {opcode} does not match {serializer_class.__name__}; "
                "storing it verbatim.",
                exc_info=True,
            )
            return UnknownOpSerializer.model_validate(data)
    raise ValueError(f"Cannot parse mantle op from {type(data).__name__}.")


MantleOpSerializerField = Annotated[MantleOpSerializerVariants, BeforeValidator(_parse_mantle_op)]
