from collections.abc import Iterable
from datetime import datetime

from wantlist.adapters.token_store import StoredAuth
from wantlist.ports.spotify import ReauthRequired, SpotifyTokens
from wantlist.ports.spotify_api import Play, SavedAlbum


class StubTokens:
    """Access-token provider double. `fail=True` simulates the 6-month re-auth."""

    def __init__(self, token: str = "tok", fail: bool = False) -> None:
        self._token = token
        self._fail = fail

    def valid_access_token(self) -> str:
        if self._fail:
            raise ReauthRequired
        return self._token


class StubSpotifyApiClient:
    def __init__(
        self,
        albums: Iterable[SavedAlbum] = (),
        plays: Iterable[Play] = (),
        followed: Iterable[str] = (),
        artist_albums: dict[str, list[SavedAlbum]] | None = None,
    ) -> None:
        self._albums = list(albums)
        self._plays = list(plays)
        self._followed = list(followed)
        self._artist_albums = artist_albums or {}
        self.saved_calls: list[str] = []

    def saved_albums(self, access_token: str) -> Iterable[SavedAlbum]:
        return list(self._albums)

    def album_isrcs(self, access_token: str, album_id: str) -> list[str]:
        return []

    def recently_played(self, access_token: str) -> list[Play]:
        return list(self._plays)

    def followed_artist_ids(self, access_token: str) -> list[str]:
        return list(self._followed)

    def artist_albums(self, access_token: str, artist_id: str) -> list[SavedAlbum]:
        return list(self._artist_albums.get(artist_id, []))

    def save_album(self, access_token: str, spotify_album_id: str) -> None:
        self.saved_calls.append(spotify_album_id)


class StubMusicBrainzResolver:
    """Resolves by album title via a mapping; everything else is the unresolvable tail."""

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._mapping = mapping or {}

    def resolve(self, *, upc: str | None, isrcs: list[str], artist: str, title: str) -> str | None:
        return self._mapping.get(title)


class StubOwnedReleaseGroups:
    def __init__(self, owned: set[str]) -> None:
        self._owned = owned

    def owned_release_group_ids(self) -> set[str]:
        return set(self._owned)


def fake_fetch_image(url: str) -> tuple[str, bytes]:
    return "image/jpeg", b"IMG:" + url.encode()


class FrozenClock:
    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed


class StubSpotifyAuthClient:
    """In-memory Spotify OAuth double. `fail_refresh=True` simulates the 6-month expiry."""

    def __init__(self, *, fail_refresh: bool = False) -> None:
        self.fail_refresh = fail_refresh
        self.exchanged: list[str] = []

    def authorize_url(self, state: str) -> str:
        return f"https://accounts.example/authorize?state={state}"

    def exchange_code(self, code: str) -> SpotifyTokens:
        self.exchanged.append(code)
        return SpotifyTokens(access_token="access-1", refresh_token="refresh-1", expires_in=3600)

    def refresh(self, refresh_token: str) -> SpotifyTokens:
        if self.fail_refresh:
            raise ReauthRequired
        return SpotifyTokens(access_token="access-2", refresh_token=refresh_token, expires_in=3600)


class FakeTokenStore:
    """In-memory token store implementing the TokenStore interface."""

    def __init__(self) -> None:
        self._auth = StoredAuth(None, None, None, None)
        self.scopes: str | None = None

    def load(self) -> StoredAuth:
        return self._auth

    def save_authorization(
        self,
        *,
        access_token: str,
        refresh_token: str,
        access_expires_at: datetime,
        authorized_at: datetime,
        scopes: str,
    ) -> None:
        self._auth = StoredAuth(access_token, refresh_token, access_expires_at, authorized_at)
        self.scopes = scopes

    def save_refreshed(self, *, access_token: str, access_expires_at: datetime) -> None:
        self._auth = StoredAuth(
            access_token, self._auth.refresh_token, access_expires_at, self._auth.authorized_at
        )

    def clear(self) -> None:
        self._auth = StoredAuth(None, None, None, None)
