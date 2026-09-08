from collections.abc import Iterable
from datetime import datetime

from wantlist.adapters.beets import BeetsAlbum
from wantlist.adapters.token_store import StoredAuth
from wantlist.ports.spotify import ReauthRequired, SpotifyTokens
from wantlist.ports.spotify_api import Play, SavedAlbum
from wantlist.ports.transmission import Torrent


class StubTokens:
    """Access-token provider double. `fail=True` simulates the 6-month re-auth."""

    def __init__(
        self, token: str = "tok", fail: bool = False, fail_after: int | None = None
    ) -> None:
        self._token = token
        self._fail = fail
        self._fail_after = fail_after  # raise ReauthRequired once this many tokens have been issued
        self.calls = 0

    def valid_access_token(self) -> str:
        if self._fail or (self._fail_after is not None and self.calls >= self._fail_after):
            raise ReauthRequired
        self.calls += 1
        return self._token


class StubSpotifyApiClient:
    def __init__(
        self,
        albums: Iterable[SavedAlbum] = (),
        plays: Iterable[Play] = (),
        followed: Iterable[str] = (),
        artist_albums: dict[str, list[SavedAlbum]] | None = None,
        search: dict[str, SavedAlbum] | None = None,
    ) -> None:
        self._albums = list(albums)
        self._plays = list(plays)
        self._followed = list(followed)
        self._artist_albums = artist_albums or {}
        self._search = search or {}
        self.saved_calls: list[str] = []

    def saved_albums(self, access_token: str) -> Iterable[SavedAlbum]:
        return list(self._albums)

    def search_album(self, access_token: str, query: str) -> SavedAlbum | None:
        return self._search.get(query)

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


class RecordingEventSink:
    """Captures emitted activity events so a test can assert what the worker reported."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, str, int | None]] = []

    def emit(self, *, job: str, type: str, message: str, album_id: int | None = None) -> None:
        self.events.append((job, type, message, album_id))


class StubLibraryCatalog:
    """A fake beets catalogue for the D17 link-candidate / possibly-owned assist."""

    def __init__(self, albums: Iterable[BeetsAlbum] = ()) -> None:
        self._albums = list(albums)

    def all_albums(self) -> list[BeetsAlbum]:
        return list(self._albums)


class StubTransmissionClient:
    def __init__(self, torrents: Iterable[Torrent] = ()) -> None:
        self._torrents = list(torrents)

    def completed_torrents(self) -> list[Torrent]:
        return list(self._torrents)


class RecordingBeetsClient:
    """Records the folders handed to `import_dir` (used to assert the import ran)."""

    def __init__(self) -> None:
        self.imported: list[str] = []

    def import_dir(self, path: str) -> None:
        self.imported.append(path)


class FakeBeetsLibrary:
    """Both the import seam and the catalogue: import_dir 'adds' a preset album to the library
    so before/after diffs work in tests (used for the D21 reverse-match)."""

    def __init__(self, adds_on_import: BeetsAlbum | None = None) -> None:
        self._albums: list[BeetsAlbum] = []
        self._adds = adds_on_import
        self.imported: list[str] = []

    def import_dir(self, path: str) -> None:
        self.imported.append(path)
        if self._adds is not None:
            self._albums.append(self._adds)

    def all_albums(self) -> list[BeetsAlbum]:
        return list(self._albums)


class FakeFileTransfer:
    """Stands in for rsync: copies the listed files from a local `download_dir` into `dest`,
    leaving the source untouched (mirrors rsync's copy-only, seeding-safe behaviour)."""

    def fetch(self, *, download_dir: str, files: list[str], dest: str) -> None:
        import shutil
        from pathlib import Path

        for rel in files:
            target = Path(dest) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(download_dir) / rel, target)


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
