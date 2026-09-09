from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.token_store import TokenStore

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def test_save_and_load_roundtrip(pg_session_factory: sessionmaker[Session]) -> None:
    store = TokenStore(pg_session_factory)
    store.clear()
    store.save_authorization(
        access_token="a",
        refresh_token="r",
        access_expires_at=NOW + timedelta(hours=1),
        authorized_at=NOW,
        scopes="user-library-read",
    )
    loaded = store.load()
    assert loaded.access_token == "a"
    assert loaded.refresh_token == "r"
    assert loaded.authorized_at == NOW


def test_refresh_does_not_change_authorized_at(pg_session_factory: sessionmaker[Session]) -> None:
    store = TokenStore(pg_session_factory)
    store.clear()
    store.save_authorization(
        access_token="a",
        refresh_token="r",
        access_expires_at=NOW,
        authorized_at=NOW,
        scopes="s",
    )
    store.save_refreshed(access_token="a2", access_expires_at=NOW + timedelta(hours=1))
    loaded = store.load()
    assert loaded.access_token == "a2"
    assert loaded.authorized_at == NOW  # a refresh must not reset the 6-month clock
