import pytest
from fastapi.testclient import TestClient

from mcm import health
from mcm.app import create_app
from mcm.config import Settings


def _client(monkeypatch: pytest.MonkeyPatch, *, postgres: bool) -> TestClient:
    monkeypatch.setattr(health, "check_postgres", lambda engine: postgres)
    return TestClient(create_app(Settings()))


def test_health_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _client(monkeypatch, postgres=True).get("/health")
    assert resp.status_code == 200
    # postgres only — the API never runs beets, so beets liveness isn't part of this check
    assert resp.json() == {"status": "ok", "checks": {"postgres": True}}


def test_health_degraded_when_postgres_down(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _client(monkeypatch, postgres=False).get("/health")
    assert resp.status_code == 503
    assert resp.json()["checks"] == {"postgres": False}
