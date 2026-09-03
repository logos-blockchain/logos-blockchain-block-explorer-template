from http.client import BAD_REQUEST

from fastapi import Query
from starlette.responses import JSONResponse, Response

from core.api import NBERequest
from models.transactions.transaction import Transaction

NOTE_ID_BYTES = 32

# How a matched field references the note, keyed by content type. Fields are
# discovered structurally (`inputs` lists and `service_note_id`), so new op
# types that reuse those field names are picked up automatically.
ROLE_LABELS = {
    ("LedgerTransfer", "inputs"): "transfer input",
    ("ChannelDeposit", "inputs"): "deposit input",
    ("ChannelWithdraw", "inputs"): "withdraw input",
    ("ChannelTransfer", "inputs"): "channel transfer input",
    ("SDPDeclare", "service_note_id"): "service note",
    ("SDPWithdraw", "service_note_id"): "service note",
}


def find_note_references(transaction: Transaction, note_id: bytes) -> list[dict]:
    """Operations in `transaction` that reference `note_id`, with field-level detail.

    Note ids appear as spend references: entries of an `inputs` list
    (LedgerTransfer, ChannelDeposit/Withdraw/Transfer) or a `service_note_id`
    field (SDP ops; called locked_note_id before node 0.3.0). Output notes carry no id in the data, so they can't match.
    """
    matches: list[dict] = []
    for op_index, operation in enumerate(transaction.operations):
        content = operation.content
        op_type = content.type

        inputs = getattr(content, "inputs", None)
        if isinstance(inputs, list):
            for input_index, candidate in enumerate(inputs):
                if candidate == note_id:
                    matches.append(
                        {
                            "op_index": op_index,
                            "op_type": op_type,
                            "field": "inputs",
                            "input_index": input_index,
                            "role": ROLE_LABELS.get((op_type, "inputs"), "input"),
                        }
                    )

        if getattr(content, "service_note_id", None) == note_id:
            matches.append(
                {
                    "op_index": op_index,
                    "op_type": op_type,
                    "field": "service_note_id",
                    "input_index": None,
                    "role": ROLE_LABELS.get((op_type, "service_note_id"), "service note"),
                }
            )
    return matches


def _parse_note_id(raw: str) -> bytes | None:
    cleaned = raw.strip().lower().removeprefix("0x")
    try:
        note_id = bytes.fromhex(cleaned)
    except ValueError:
        return None
    return note_id if len(note_id) == NOTE_ID_BYTES else None


async def search(
    request: NBERequest,
    note_id: str,
    fork: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
) -> Response:
    """Transactions containing an operation that references the note id, newest first."""
    note = _parse_note_id(note_id)
    if note is None:
        return JSONResponse(
            {"detail": f"note_id must be {NOTE_ID_BYTES} bytes of hex ({NOTE_ID_BYTES * 2} characters)"},
            status_code=BAD_REQUEST,
        )

    candidates = await request.app.state.transaction_repository.search_by_note_id(note, fork=fork, limit=limit)

    results = []
    for transaction in candidates:
        matches = find_note_references(transaction, note)
        if not matches:
            continue  # hex appeared in a non-note field (signature, key, metadata)
        results.append(
            {
                "hash": transaction.hash.hex(),
                "block_hash": transaction.block.hash.hex(),
                "height": transaction.block.height,
                "slot": transaction.block.slot,
                "matches": matches,
            }
        )

    return JSONResponse(
        {
            "note_id": note.hex(),
            "count": len(results),
            "limit": limit,
            "transactions": results,
        }
    )
