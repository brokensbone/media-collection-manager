from datetime import UTC, datetime, timedelta

import pytest

from wantlist.auth_service import AuthService
from wantlist.ports.spotify import ReauthRequired

from .fakes import FakeTokenStore, FrozenClock, StubSpotifyAuthClient

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _service(store: FakeTokenStore, client: StubSpotifyAuthClient) -> AuthService:
    return AuthService(
        client=client,  # type: ignore[arg-type]
        store=store,  # type: ignore[arg-type]
        clock=FrozenClock(NOW),
        scopes="user-library-read",
        lifetime_days=183,
        warn_days=21,
    )


def test_complete_login_stores_authorization() -> None:
    store = FakeTokenStore()
    _service(store, StubSpotifyAuthClient()).complete_login("code")
    loaded = store.load()
    assert loaded.refresh_token == "refresh-1"
    assert loaded.authorized_at == NOW
    assert store.scopes == "user-library-read"


def test_valid_access_token_returns_cached_when_fresh() -> None:
    store = FakeTokenStore()
    svc = _service(store, StubSpotifyAuthClient())
    svc.complete_login("code")  # access valid for 3600s from NOW
    assert svc.valid_access_token() == "access-1"


def test_valid_access_token_refreshes_when_expired() -> None:
    store = FakeTokenStore()
    client = StubSpotifyAuthClient()
    store.save_authorization(
        access_token="old",
        refresh_token="refresh-1",
        access_expires_at=NOW - timedelta(minutes=5),  # already expired
        authorized_at=NOW - timedelta(days=10),
        scopes="user-library-read",
    )
    assert _service(store, client).valid_access_token() == "access-2"


def test_expired_refresh_token_clears_and_raises_reauth() -> None:
    store = FakeTokenStore()
    store.save_authorization(
        access_token="old",
        refresh_token="refresh-1",
        access_expires_at=NOW - timedelta(minutes=5),
        authorized_at=NOW - timedelta(days=200),
        scopes="user-library-read",
    )
    svc = _service(store, StubSpotifyAuthClient(fail_refresh=True))
    with pytest.raises(ReauthRequired):
        svc.valid_access_token()
    assert store.load().refresh_token is None  # cleared → status will show disconnected
    assert svc.status().connected is False


def test_status_reports_countdown() -> None:
    store = FakeTokenStore()
    store.save_authorization(
        access_token="a",
        refresh_token="r",
        access_expires_at=NOW + timedelta(hours=1),
        authorized_at=NOW - timedelta(days=100),
        scopes="user-library-read",
    )
    status = _service(store, StubSpotifyAuthClient()).status()
    assert status.connected is True
    assert status.reauth_in_days == 83
