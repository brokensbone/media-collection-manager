import logging
from collections.abc import Callable
from dataclasses import dataclass

from .adapters.album_repo import AlbumRepo
from .ports.spotify import AccessTokenProvider, ReauthRequired
from .ports.spotify_api import SpotifyApiClient

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    added: int
    skipped: int
    paused: bool  # True when skipped because Spotify needs re-auth (§8c)


class IngestService:
    """Pull saved albums into `album` rows (deduped) and fetch their cover art (§4/§4b)."""

    def __init__(
        self,
        *,
        api: SpotifyApiClient,
        repo: AlbumRepo,
        tokens: AccessTokenProvider,
        fetch_image: Callable[[str], tuple[str, bytes]],
    ) -> None:
        self._api = api
        self._repo = repo
        self._tokens = tokens
        self._fetch_image = fetch_image

    def ingest_saves(self) -> IngestResult:
        try:
            token = self._tokens.valid_access_token()
        except ReauthRequired:
            log.warning("Spotify re-auth required; skipping saves ingest")
            return IngestResult(added=0, skipped=0, paused=True)

        existing = self._repo.existing_spotify_ids()  # dedupe by spotify id (§4)
        added = skipped = 0
        for album in self._api.saved_albums(token):
            if album.spotify_id in existing:
                skipped += 1
                continue
            self._repo.add_saved_album(
                spotify_id=album.spotify_id,
                artist=album.artist,
                title=album.title,
                upc=album.upc,
                added_at=album.added_at,
                art_url=album.art_url,
            )
            existing.add(album.spotify_id)
            added += 1
        return IngestResult(added=added, skipped=skipped, paused=False)

    def fetch_missing_art(self) -> int:
        stored = 0
        for album_id, url in self._repo.albums_missing_art():
            try:
                content_type, data = self._fetch_image(url)
            except Exception:
                log.exception("cover art fetch failed for album %s", album_id)
                continue
            self._repo.save_art(album_id, content_type, data)
            stored += 1
        return stored
