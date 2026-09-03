"""Settings come from LBE_* variables, with the pre-rename NBE_* names accepted as aliases."""

import pytest

from core.settings import Settings

ALL_NAMES = [
    "HOST", "PORT", "BASE_PATH", "NODE_API_HOST", "NODE_API_PORT", "NODE_API_PROTOCOL", "NODE_API_TIMEOUT",
    "NODE_API_AUTH", "DATABASE_PATH", "DATABASE_URL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ALL_NAMES:
        monkeypatch.delenv(f"LBE_{name}", raising=False)
        monkeypatch.delenv(f"NBE_{name}", raising=False)


def test_defaults():
    settings = Settings.from_env()
    assert (settings.host, settings.port, settings.base_path) == ("0.0.0.0", 8000, "")
    assert (settings.node_api_host, settings.node_api_port) == ("127.0.0.1", 8080)
    assert settings.node_api_auth is None
    assert settings.database_path.endswith("sqlite.db")


def test_lbe_variables(monkeypatch):
    monkeypatch.setenv("LBE_NODE_API_HOST", "node-0")
    monkeypatch.setenv("LBE_NODE_API_PORT", "18080")
    monkeypatch.setenv("LBE_BASE_PATH", "/web/explorer/")
    monkeypatch.setenv("LBE_DATABASE_PATH", "/node-data/explorer/sqlite.db")
    monkeypatch.setenv("LBE_NODE_API_AUTH", "Basic dXNlcjpwYXNz")  # user:pass

    settings = Settings.from_env()
    assert (settings.node_api_host, settings.node_api_port, settings.base_path) == ("node-0", 18080, "/web/explorer")
    assert settings.database_path == "/node-data/explorer/sqlite.db"
    assert settings.node_api_auth is not None


def test_legacy_nbe_variables_are_aliases(monkeypatch, caplog):
    # The shape of deployment/compose.run.yml in logos-blockchain today.
    monkeypatch.setenv("NBE_NODE_API_HOST", "logos-blockchain-node-0")
    monkeypatch.setenv("NBE_NODE_API_PORT", "18080")
    monkeypatch.setenv("NBE_BASE_PATH", "/web/explorer")
    monkeypatch.setenv("NBE_DATABASE_URL", "sqlite:////node-data/explorer/sqlite.db")

    with caplog.at_level("WARNING"):
        settings = Settings.from_env()

    assert (settings.node_api_host, settings.node_api_port, settings.base_path) == (
        "logos-blockchain-node-0", 18080, "/web/explorer",
    )
    assert settings.database_path == "/node-data/explorer/sqlite.db"
    assert "NBE_NODE_API_HOST is deprecated" in caplog.text
    assert "NBE_DATABASE_URL is deprecated" in caplog.text


def test_lbe_wins_over_nbe(monkeypatch):
    monkeypatch.setenv("NBE_NODE_API_HOST", "old")
    monkeypatch.setenv("LBE_NODE_API_HOST", "new")
    monkeypatch.setenv("NBE_DATABASE_URL", "sqlite:///old.db")
    monkeypatch.setenv("LBE_DATABASE_PATH", "new.db")
    settings = Settings.from_env()
    assert (settings.node_api_host, settings.database_path) == ("new", "new.db")


def test_non_sqlite_legacy_url_is_rejected(monkeypatch):
    monkeypatch.setenv("NBE_DATABASE_URL", "postgresql://x")
    with pytest.raises(ValueError):
        Settings.from_env()
