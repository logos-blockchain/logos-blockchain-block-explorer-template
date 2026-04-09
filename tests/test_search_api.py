"""Tests for Search API endpoint."""

import pytest
from fastapi.testclient import TestClient
from src.app import create_app

app = create_app("")
client = TestClient(app)


@pytest.mark.asyncio
async def test_search_block_hash():
    response = client.get("/api/v1/search/0x" + "00" * 32)
    # Should return 404 for non-existent block
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_transaction_hash():
    response = client.get("/api/v1/search/0x" + "11" * 32)
    # Should return 404 for non-existent transaction
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_invalid_hash():
    response = client.get("/api/v1/search/invalid")
    assert response.status_code == 400
