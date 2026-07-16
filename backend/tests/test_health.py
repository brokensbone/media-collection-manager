import pytest
from fastapi.testclient import TestClient

from wantlist import health
from wantlist.app import create_app
from wantlist.config import Settings


def _client(monkeypatch: pytest.MonkeyPatch, *, postgres: bool, beets: bool) -> TestClient:
    monkeypatch.setattr(health, "check_postgres", lambda engine: postgres)
    monkeypatch.setattr(health, "check_beets", lambda: beets)
    return TestClient(create_app(Settings()))


def test_health_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _client(monkeypatch, postgres=True, beets=True).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"postgres": True, "beets": True}}


def test_health_degraded_when_postgres_down(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _client(monkeypatch, postgres=False, beets=True).get("/health")
    assert resp.status_code == 503
    assert resp.json()["checks"] == {"postgres": False, "beets": True}


def test_health_degraded_when_beets_down(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _client(monkeypatch, postgres=True, beets=False).get("/health")
    assert resp.status_code == 503
    assert resp.json()["checks"] == {"postgres": True, "beets": False}
