"""The combined live stream: one connection carrying health, blocks and transactions."""

import asyncio
import json
from types import SimpleNamespace
from urllib.parse import urlencode

from starlette.requests import Request

from api.v1 import live
from core.notifier import ChainNotifier
from db import Database
from models.health import Health
from models.transactions.transaction import Transaction
from test_chain import GENESIS, make_block


class FakeNode:
    async def get_health(self) -> Health:
        return Health(healthy=True)


async def open_stream(db: Database, notifier: ChainNotifier, **query):
    """The stream's body, as an iterator of parsed lines (waiting at most 2 s for each)."""
    app = SimpleNamespace(state=SimpleNamespace(db=db, notifier=notifier, node_api=FakeNode()))
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": urlencode(query).encode()}
    body = (await live.stream(Request({**scope, "app": app}))).body_iterator
    try:
        while True:
            chunk = await asyncio.wait_for(anext(body), timeout=2)
            for line in chunk.decode().splitlines():
                yield json.loads(line)
    finally:
        await body.aclose()


def test_tags_each_feed_and_follows_the_chain(tmp_path):
    async def scenario():
        db = Database(str(tmp_path / "test.db"))
        notifier = ChainNotifier()
        genesis = make_block(GENESIS, parent=b"\x00", slot=0)
        genesis.transactions = [Transaction.model_validate({"hash": b"\x0a" * 32, "operations": []})]
        db.store_blocks([genesis])
        db.set_canonical_tip(GENESIS)

        lines = open_stream(db, notifier, blocks=5, transactions=5)
        bootstrap = {item["topic"]: item["data"] for item in [await anext(lines) for _ in range(3)]}
        assert bootstrap["health"] == {"healthy": True}
        assert bootstrap["block"]["hash"] == GENESIS.hex()
        assert bootstrap["transaction"]["hash"] == (b"\x0a" * 32).hex()

        db.store_blocks([make_block(b"\x02", parent=GENESIS, slot=1)])
        db.set_canonical_tip(b"\x02")
        await notifier.publish()
        update = await anext(lines)
        assert (update["topic"], update["data"]["hash"]) == ("block", "02")
        await lines.aclose()

    asyncio.run(scenario())


def test_without_tables_carries_only_health(tmp_path):
    async def scenario():
        lines = open_stream(Database(str(tmp_path / "test.db")), ChainNotifier())
        assert (await anext(lines))["topic"] == "health"
        await lines.aclose()

    asyncio.run(scenario())
