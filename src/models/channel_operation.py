from typing import TYPE_CHECKING, Iterator, Optional

from core.models import LbeSchema
from core.types import HexBytes

if TYPE_CHECKING:
    from models.transactions.transaction import Transaction

# Content types that belong to a channel.
CHANNEL_CONTENT_TYPES = frozenset(
    {"ChannelInscribe", "ChannelConfig", "ChannelDeposit", "ChannelWithdraw", "ChannelTransfer"}
)


def channel_id_of(content) -> Optional[bytes]:
    """Channel id referenced by an operation content, if it is a channel op.

    ChannelConfig carries the id as `channel`; the rest as `channel_id`.
    """
    if getattr(content, "type", None) not in CHANNEL_CONTENT_TYPES:
        return None
    channel = getattr(content, "channel_id", None)
    if channel is None:
        channel = getattr(content, "channel", None)
    if channel is None:
        return None
    return channel if isinstance(channel, bytes) else bytes.fromhex(str(channel))


class ChannelOperation(LbeSchema):
    """One channel operation, indexed at ingestion time.

    Channel activity used to be aggregated on every request from the JSON of
    the most recent N transactions, which mis-counted long-lived channels and
    dropped any channel whose activity fell outside the window. These rows are
    written in the same transaction as their block, so counts are exact and
    queries can restrict to canonical blocks.
    """

    id: Optional[int] = None
    block_id: int
    transaction_id: int
    channel_id: HexBytes
    op_type: str
    # Position of the op inside its transaction's `operations` list.
    op_index: int

    def __repr__(self) -> str:
        return (
            f"<ChannelOperation(channel={self.channel_id.hex()[:16]}..., tx={self.transaction_id}, "
            f"op_index={self.op_index}, type={self.op_type})>"
        )


def channel_operations_of(transaction: "Transaction") -> Iterator[ChannelOperation]:
    """Channel operation rows for a persisted transaction (ids must be assigned)."""
    for op_index, operation in enumerate(transaction.operations):
        channel_id = channel_id_of(operation.content)
        if channel_id is None:
            continue
        yield ChannelOperation(
            block_id=transaction.block_id,
            transaction_id=transaction.id,
            channel_id=channel_id,
            op_type=operation.content.type,
            op_index=op_index,
        )

