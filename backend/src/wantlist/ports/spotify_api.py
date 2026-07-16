from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class SavedAlbum:
    spotify_id: str
    artist: str
    title: str
    upc: str | None
    added_at: datetime | None
    art_url: str | None


class SpotifyApiClient(Protocol):
    """Read-only Spotify data we depend on (SPEC §4). Base URL is injected (§14)."""

    def saved_albums(self, access_token: str) -> Iterable[SavedAlbum]: ...
