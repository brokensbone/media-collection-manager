from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from ..models import SpotifyAuth

_ROW_ID = 1  # single-row token store


@dataclass
class StoredAuth:
    access_token: str | None
    refresh_token: str | None
    access_expires_at: datetime | None
    authorized_at: datetime | None


class TokenStore:
    """Persists the single Spotify token row (SPEC §4/§8c)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def load(self) -> StoredAuth:
        with self._session_factory() as session:
            row = session.get(SpotifyAuth, _ROW_ID)
            if row is None:
                return StoredAuth(None, None, None, None)
            return StoredAuth(
                access_token=row.access_token,
                refresh_token=row.refresh_token,
                access_expires_at=row.access_expires_at,
                authorized_at=row.authorized_at,
            )

    def save_authorization(
        self,
        *,
        access_token: str,
        refresh_token: str,
        access_expires_at: datetime,
        authorized_at: datetime,
        scopes: str,
    ) -> None:
        """A full (re-)authorization: resets authorized_at, which starts a new 6-month clock."""
        with self._session_factory() as session:
            row = self._get_or_create(session)
            row.access_token = access_token
            row.refresh_token = refresh_token
            row.access_expires_at = access_expires_at
            row.authorized_at = authorized_at
            row.scopes = scopes
            session.commit()

    def save_refreshed(self, *, access_token: str, access_expires_at: datetime) -> None:
        """A token refresh only updates the access token — NOT authorized_at (§8c)."""
        with self._session_factory() as session:
            row = self._get_or_create(session)
            row.access_token = access_token
            row.access_expires_at = access_expires_at
            session.commit()

    def clear(self) -> None:
        with self._session_factory() as session:
            row = session.get(SpotifyAuth, _ROW_ID)
            if row is not None:
                session.delete(row)
                session.commit()

    def _get_or_create(self, session: Session) -> SpotifyAuth:
        row = session.get(SpotifyAuth, _ROW_ID)
        if row is None:
            row = SpotifyAuth(id=_ROW_ID)
            session.add(row)
        return row
