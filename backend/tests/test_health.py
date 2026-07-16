import pytest
from fastapi.testclient import TestClient

from wantlist import health
from wantlist.app import create_app
from wantlist.config import Settings


def _client(monkeypatch: pytest.MonkeyPatch, *, postgres: bool, beets_command: str) -> TestClient:
    monkeypatch.setattr(health, "check_postgres", lambda engine: postgres)
    return TestClient(create_app(Settings(beets_command=beets_command)))


def test_health_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, postgres=True, beets_command="true")
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"postgres": True, "beets": True}}


def test_health_degraded_when_postgres_down(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, postgres=False, beets_command="true")
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["checks"] == {"postgres": False, "beets": True}


def test_health_degraded_when_beets_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, postgres=True, beets_command="definitely-not-a-real-command-xyz")
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["checks"] == {"postgres": True, "beets": False}
