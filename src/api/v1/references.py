"""Search transactions by a note id or public key they name, through the ingestion-time reference index."""

from http.client import BAD_REQUEST

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from api.http import query_int
from models.transactions.references import ReferenceKind

KEY_BYTES = 32

# How a matched field references the note or key, keyed by content type and field.
# Fields without an entry are labelled by their name.
ROLE_LABELS = {
    ("LedgerTransfer", "inputs"): "transfer input",
    ("ChannelDeposit", "inputs"): "deposit input",
    ("ChannelWithdraw", "inputs"): "withdraw input",
    ("ChannelTransfer", "inputs"): "channel transfer input",
    ("SDPDeclare", "service_note_id"): "service note",
    ("SDPWithdraw", "service_note_id"): "service note",
    ("LedgerTransfer", "outputs"): "transfer output",
    ("ChannelTransfer", "outputs"): "channel transfer output",
    ("ChannelInscribe", "signer"): "inscription signer",
    ("ChannelConfig", "keys"): "channel key",
    ("SDPDeclare", "provider_id"): "SDP provider",
    ("SDPDeclare", "zk_id"): "SDP zk key",
    ("LeaderClaim", "pk"): "leader claim",
    ("ClaimPowReward", "public_key"): "PoW reward claimant",
}


def _parse_key(raw: str) -> bytes | None:
    cleaned = raw.strip().lower().removeprefix("0x")
    try:
        key = bytes.fromhex(cleaned)
    except ValueError:
        return None
    return key if len(key) == KEY_BYTES else None


def _search(request: Request, kind: ReferenceKind, raw_key: str, name: str) -> Response:
    """Canonical transactions naming the key, newest first, each with the fields that name it."""
    limit = query_int(request, "limit", 50, ge=1, le=200)
    key = _parse_key(raw_key)
    if key is None:
        return JSONResponse(
            {"detail": f"{name} must be {KEY_BYTES} bytes of hex ({KEY_BYTES * 2} characters)"},
            status_code=BAD_REQUEST,
        )

    results = []
    for transaction, block, references in request.app.state.db.transactions_referencing(kind, key, limit=limit):
        matches = []
        for reference in references:
            op_type = transaction.operations[reference.op_index].content.type
            matches.append(
                {
                    "op_index": reference.op_index,
                    "op_type": op_type,
                    "field": reference.field,
                    "item_index": reference.item_index,
                    "role": ROLE_LABELS.get((op_type, reference.field), reference.field),
                }
            )
        results.append(
            {
                "hash": transaction.hash.hex(),
                "block_hash": block.hash.hex(),
                "height": block.height,
                "slot": block.slot,
                "matches": matches,
            }
        )

    return JSONResponse(
        {"kind": kind, "key": key.hex(), "count": len(results), "limit": limit, "transactions": results}
    )


async def search_note(request: Request) -> Response:
    """Transactions spending the note (as an input or SDP service note)."""
    return _search(request, "note", request.path_params["note_id"], "note_id")


async def search_public_key(request: Request) -> Response:
    """Transactions naming the key: as a note's owner, signer, channel key, SDP key or reward claimant."""
    return _search(request, "public_key", request.path_params["public_key"], "public_key")
