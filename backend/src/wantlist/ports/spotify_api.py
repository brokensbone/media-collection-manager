from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class SavedAlbum:
    spotify_id: str
    artist: str
    artist_id: str | None
    title: str
    upc: str | None
    added_at: datetime | None
    art_url: str | None
    album_type: str | None = None


@dataclass
class Play:
    spotify_track_id: str
    spotify_album_id: str | None
    played_at: datetime


class SpotifyApiClient(Protocol):
    """Read-only Spotify data we depend on (SPEC §4). Base URL is injected (§14)."""

    def saved_albums(self, access_token: str) -> Iterable[SavedAlbum]: ...

    def search_album(self, access_token: str, query: str) -> SavedAlbum | None: ...

    def album_isrcs(self, access_token: str, album_id: str) -> list[str]: ...

    def recently_played(self, access_token: str) -> list[Play]: ...

    def followed_artist_ids(self, access_token: str) -> list[str]: ...

    def artist_albums(self, access_token: str, artist_id: str) -> list[SavedAlbum]: ...

    def save_album(self, access_token: str, spotify_album_id: str) -> None: ...
