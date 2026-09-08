import logging
from dataclasses import dataclass

from .adapters.album_repo import AlbumRepo
from .adapters.event_log import NullEventSink
from .ports.events import EventSink
from .ports.spotify import AccessTokenProvider, ReauthRequired
from .ports.spotify_api import SpotifyApiClient

log = logging.getLogger(__name__)


@dataclass
class WatchResult:
    added: int
    artists: int
    baselined: int
    paused: bool


class ArtistWatchService:
    """Surface *genuinely new* releases from watched artists as `suggested` (SPEC §6b).

    Seed = followed artists ∪ artists of kept albums. An artist's FIRST watch **baselines**
    it: the whole current catalogue is recorded as seen and nothing is surfaced (no
    back-catalogue flood). Later runs surface only album ids not seen before."""

    def __init__(
        self,
        *,
        api: SpotifyApiClient,
        repo: AlbumRepo,
        tokens: AccessTokenProvider,
        events: EventSink | None = None,
    ) -> None:
        self._api = api
        self._repo = repo
        self._tokens = tokens
        self._events = events or NullEventSink()

    def poll(self) -> WatchResult:
        try:
            token = self._tokens.valid_access_token()
        except ReauthRequired:
            log.warning("Spotify re-auth required; skipping artist watch")
            return WatchResult(added=0, artists=0, baselined=0, paused=True)

        artist_ids = set(self._api.followed_artist_ids(token)) | self._repo.kept_artist_ids()
        seen = self._repo.seen_album_ids()
        existing = self._repo.existing_spotify_ids()
        added = 0
        baselined = 0

        for artist_id in artist_ids:
            try:
                # Refresh per artist: scanning many artists can outlive the access token, and
                # this returns a fresh one (refreshing ~60s before expiry) so no call 401s.
                token = self._tokens.valid_access_token()
            except ReauthRequired:
                log.warning("Spotify re-auth required; pausing artist watch")
                return WatchResult(
                    added=added, artists=len(artist_ids), baselined=baselined, paused=True
                )
            is_baseline = not self._repo.artist_has_baseline(artist_id)
            to_mark: list[tuple[str, str]] = []
            for album in self._api.artist_albums(token, artist_id):
                sid = album.spotify_id
                if sid in seen:
                    continue
                seen.add(sid)
                to_mark.append((sid, artist_id))
                # Baseline run records everything silently; already-tracked albums are never
                # re-surfaced; otherwise a genuinely new release becomes a suggestion.
                if not is_baseline and sid not in existing:
                    self._repo.add_suggested_album(
                        spotify_id=sid,
                        artist=album.artist,
                        artist_id=album.artist_id,
                        title=album.title,
                        art_url=album.art_url,
                        album_type=album.album_type,
                    )
                    added += 1
                    self._events.emit(
                        job="artist_watch",
                        type="suggested",
                        message=f"New release from {album.artist}: '{album.title}'",
                    )
            self._repo.mark_seen(to_mark)
            if is_baseline:
                baselined += 1
        return WatchResult(added=added, artists=len(artist_ids), baselined=baselined, paused=False)
