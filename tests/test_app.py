"""Routing and base-path handling of the assembled app (no node, no lifespan)."""

import sqlite3
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app import create_app
from core.settings import Settings
from db import Database


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(base_path="/web/explorer"))
    app.state.db = Database(str(tmp_path / "test.db"))
    # TestClient runs the app on another thread; the explorer itself is single-threaded.
    app.state.db.conn = sqlite3.connect(str(tmp_path / "test.db"), check_same_thread=False)
    app.state.notifier = SimpleNamespace()
    return TestClient(app)  # no `with`: the lifespan (node sync) does not run


def test_api_routes_match_with_and_without_the_prefix(client):
    # The deployment's nginx forwards the prefixed path unchanged; direct access has no prefix.
    assert client.get("/web/explorer/api/v1/").json() == {"version": "1"}
    assert client.get("/api/v1/").json() == {"version": "1"}
    assert client.get("/web/explorer/api/v1/blocks/list").json()["total_count"] == 0


def test_spa_is_served_with_the_prefix_as_base_href(client):
    html = client.get("/web/explorer/blocks/abc").text
    assert '<base href="/web/explorer/" />' in html


def test_unknown_api_and_static_paths_are_404_not_spa(client):
    assert client.get("/web/explorer/api/v1/nope").status_code == 404
    assert client.get("/web/explorer/api/v1/nope").json() == {"detail": "Not Found"}
    assert client.get("/static/nope.js").status_code == 404


def test_bad_query_parameters_are_400(client):
    response = client.get("/api/v1/blocks/list?page-size=abc")
    assert response.status_code == 400
    assert "page-size" in response.json()["detail"]
