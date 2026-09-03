from typing import TYPE_CHECKING, Iterable, Iterator, List, Optional

from sqlmodel import Field

from core.models import IdNbeModel
from core.types import HexBytes

if TYPE_CHECKING:
    from models.block import Block
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


class ChannelOperation(IdNbeModel, table=True):
    """One channel operation, indexed at ingestion time.

    Channel activity used to be aggregated on every request from the JSON of
    the most recent N transactions, which mis-counted long-lived channels and
    dropped any channel whose activity fell outside the window. This table is
    written in the same commit as its block, so counts are exact and queries
    can restrict to canonical blocks.
    """

    __tablename__ = "channel_operation"

    block_id: int = Field(foreign_key="block.id", nullable=False, index=True)
    transaction_id: int = Field(foreign_key="transaction.id", nullable=False, index=True)
    channel_id: HexBytes = Field(nullable=False, index=True)
    op_type: str = Field(nullable=False)
    # Position of the op inside its transaction's `operations` list.
    op_index: int = Field(nullable=False)

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


def channel_operations_for_blocks(blocks: Iterable["Block"]) -> List[ChannelOperation]:
    rows: List[ChannelOperation] = []
    for block in blocks:
        for transaction in block.transactions:
            rows.extend(channel_operations_of(transaction))
    return rows
