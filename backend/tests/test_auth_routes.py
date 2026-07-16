from datetime import UTC, datetime

from fastapi.testclient import TestClient

from wantlist.app import create_app
from wantlist.auth_service import AuthService
from wantlist.config import Settings

from .fakes import FakeTokenStore, FrozenClock, StubSpotifyAuthClient

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _client() -> TestClient:
    app = create_app(
        Settings(spotify_accounts_url="https://accounts.example", frontend_url="/done")
    )
    app.state.auth_service = AuthService(
        client=StubSpotifyAuthClient(),  # type: ignore[arg-type]
        store=FakeTokenStore(),  # type: ignore[arg-type]
        clock=FrozenClock(NOW),
        scopes="user-library-read",
        lifetime_days=183,
        warn_days=21,
    )
    return TestClient(app, follow_redirects=False)


def test_status_disconnected_initially() -> None:
    resp = _client().get("/auth/spotify/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


def test_login_redirects_to_spotify_and_sets_state_cookie() -> None:
    resp = _client().get("/auth/spotify/login")
    assert resp.status_code in (302, 307)
    assert "accounts.example/authorize" in resp.headers["location"]
    assert "wl_oauth_state" in resp.cookies


def test_callback_rejects_bad_state() -> None:
    client = _client()
    client.cookies.set("wl_oauth_state", "expected")
    resp = client.get("/auth/spotify/callback", params={"code": "c", "state": "different"})
    assert resp.status_code == 400


def test_callback_completes_login_then_status_connected() -> None:
    client = _client()
    client.cookies.set("wl_oauth_state", "st")
    resp = client.get("/auth/spotify/callback", params={"code": "c", "state": "st"})
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/done"
    status = client.get("/auth/spotify/status").json()
    assert status["connected"] is True
    assert status["reauth_in_days"] == 183
