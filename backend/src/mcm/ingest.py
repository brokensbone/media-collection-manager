import logging
from collections.abc import Callable
from dataclasses import dataclass

from .adapters.album_repo import AlbumRepo
from .adapters.event_log import NullEventSink
from .ports.events import EventSink
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
        events: EventSink | None = None,
    ) -> None:
        self._api = api
        self._repo = repo
        self._tokens = tokens
        self._fetch_image = fetch_image
        self._events = events or NullEventSink()

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
                artist_id=album.artist_id,
                title=album.title,
                upc=album.upc,
                added_at=album.added_at,
                art_url=album.art_url,
                album_type=album.album_type,
            )
            existing.add(album.spotify_id)
            added += 1
            self._events.emit(
                job="ingest",
                type="saved",
                message=f"New saved album: '{album.artist} — {album.title}'",
            )
        return IngestResult(added=added, skipped=skipped, paused=False)

    def backfill_owned_art(self) -> int:
        """Look owned albums that still have no cover up on Spotify to get an art_url, so the
        next fetch stores the cover. Reaches albums that arrived via Transmission/beets without
        a Spotify match (or while Spotify was disconnected). Token per item so a long run can't
        outlive it; if Spotify isn't connected, stop and retry next pass."""
        found = 0
        for album in self._repo.owned_without_art():
            try:
                token = self._tokens.valid_access_token()
            except ReauthRequired:
                break
            result = self._api.search_album(token, f"{album.artist} {album.title}")
            if result and result.art_url:
                self._repo.set_art_url(album.id, result.art_url)
                found += 1
        return found

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
