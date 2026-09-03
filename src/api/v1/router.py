from fastapi import APIRouter

from . import blocks, channels, health, index, notes, transactions


def create_v1_router() -> APIRouter:
    """
    Route order must be preserved.
    """
    router = APIRouter()

    router.add_api_route("/", index.index, methods=["GET", "HEAD"])

    router.add_api_route("/health/stream", health.stream, methods=["GET", "HEAD"])
    router.add_api_route("/health", health.get, methods=["GET", "HEAD"])

    router.add_api_route("/transactions/stream", transactions.stream, methods=["GET"])
    router.add_api_route("/transactions/list", transactions.list_transactions, methods=["GET"])
    router.add_api_route("/transactions/{transaction_hash:str}", transactions.get, methods=["GET"])

    router.add_api_route("/notes/{note_id:str}", notes.search, methods=["GET"])

    router.add_api_route("/channels/list", channels.list_channels, methods=["GET"])
    router.add_api_route("/channels/{channel_id:str}", channels.get_channel, methods=["GET"])

    router.add_api_route("/blocks/stream", blocks.stream, methods=["GET"])
    router.add_api_route("/blocks/list", blocks.list_blocks, methods=["GET"])
    router.add_api_route("/blocks/{block_hash:str}", blocks.get, methods=["GET"])

    return router
