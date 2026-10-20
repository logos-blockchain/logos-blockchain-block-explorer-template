from typing import TYPE_CHECKING, Iterator, Literal, Optional

from core.models import LbeSchema
from core.types import HexBytes

if TYPE_CHECKING:
    from models.transactions.transaction import Transaction

ReferenceKind = Literal["note", "public_key"]

# Fields that carry note ids or public keys, found structurally so new op types
# reusing these names are picked up. Note ids appear only as spend references:
# an output note carries its owner's key but no id (the id is a Poseidon hash
# the explorer does not compute), so a key's spends cannot be traced to it.
NOTE_FIELDS = ("inputs", "service_note_id")
# provider_id is the SDP provider's Ed25519 key; zk_id its zk key.
PUBLIC_KEY_FIELDS = ("signer", "keys", "pk", "public_key", "provider_id", "zk_id")


class TransactionReference(LbeSchema):
    """A note id or public key named by one field of one operation, indexed at ingestion."""

    block_id: int
    transaction_id: int
    kind: ReferenceKind
    key: HexBytes
    op_index: int
    field: str
    # Position in a list field (inputs, outputs, keys); None for single-valued fields.
    item_index: Optional[int] = None


def references_of(transaction: "Transaction") -> Iterator[TransactionReference]:
    """Reference rows for a persisted transaction (ids must be assigned)."""

    def reference(kind: ReferenceKind, key: bytes, op_index: int, field: str, item_index: Optional[int] = None):
        return TransactionReference(
            block_id=transaction.block_id,
            transaction_id=transaction.id,
            kind=kind,
            key=key,
            op_index=op_index,
            field=field,
            item_index=item_index,
        )

    for op_index, operation in enumerate(transaction.operations):
        content = operation.content
        for kind, fields in (("note", NOTE_FIELDS), ("public_key", PUBLIC_KEY_FIELDS)):
            for field in fields:
                value = getattr(content, field, None)
                if isinstance(value, bytes):
                    yield reference(kind, value, op_index, field)
                elif isinstance(value, list):
                    for item_index, item in enumerate(value):
                        if isinstance(item, bytes):
                            yield reference(kind, item, op_index, field, item_index)
        for item_index, note in enumerate(getattr(content, "outputs", None) or []):
            yield reference("public_key", note.public_key, op_index, "outputs", item_index)
