import logging
from dataclasses import dataclass

from .adapters.album_repo import AlbumRepo
from .adapters.event_log import NullEventSink
from .ports.events import EventSink
from .ports.musicbrainz import MusicBrainzResolver
from .ports.spotify import AccessTokenProvider, ReauthRequired
from .ports.spotify_api import SpotifyApiClient

log = logging.getLogger(__name__)


@dataclass
class ResolveResult:
    resolved: int
    unresolved: int
    paused: bool


class ResolutionService:
    """Resolve-once (§5): give each unresolved album a MusicBrainz release-group id, using
    its ISRCs/UPC. Unresolved albums (the MB-absent tail, §11) stay null and re-try later."""

    def __init__(
        self,
        *,
        api: SpotifyApiClient,
        resolver: MusicBrainzResolver,
        repo: AlbumRepo,
        tokens: AccessTokenProvider,
        max_per_run: int | None = None,
        events: EventSink | None = None,
    ) -> None:
        self._api = api
        self._resolver = resolver
        self._repo = repo
        self._tokens = tokens
        # Cap albums resolved per pass so a cold start (e.g. 1000 fresh saves) chips away at
        # MusicBrainz politely instead of hammering it for ~20 minutes each reconcile.
        self._max_per_run = max_per_run
        self._events = events or NullEventSink()

    def resolve_unresolved(self) -> ResolveResult:
        candidates = self._repo.albums_needing_resolution()
        if self._max_per_run is not None:
            candidates = candidates[: self._max_per_run]

        resolved = unresolved = errored = 0
        attempted_unresolved: list[int] = []
        for album in candidates:
            try:
                # Per album, not once per pass: MusicBrainz throttling makes a pass take many
                # minutes, long enough to outlive a Spotify access token. valid_access_token()
                # refreshes ~60s before expiry, so no request 401s partway through the batch.
                token = self._tokens.valid_access_token()
            except ReauthRequired:
                log.warning("Spotify re-auth required; pausing resolution")
                self._repo.bump_resolution_attempts(attempted_unresolved)
                return ResolveResult(resolved=resolved, unresolved=unresolved, paused=True)
            try:
                isrcs = self._api.album_isrcs(token, album.spotify_id) if album.spotify_id else []
                rgid = self._resolver.resolve(
                    upc=album.upc, isrcs=isrcs, artist=album.artist, title=album.title
                )
            except Exception:
                # A flaky upstream (MB 503, Spotify hiccup) must not abort the whole pass —
                # leave this one unresolved and it retries next reconcile.
                errored += 1
                unresolved += 1
                attempted_unresolved.append(album.id)
                self._events.emit(
                    job="resolution",
                    type="error",
                    message=f"Couldn't reach MusicBrainz for '{album.artist} — {album.title}'",
                    album_id=album.id,
                )
                continue
            if rgid:
                self._repo.set_release_group(album.id, rgid)
                resolved += 1
                self._events.emit(
                    job="resolution",
                    type="resolved",
                    message=f"Resolved '{album.artist} — {album.title}'",
                    album_id=album.id,
                )
            else:
                unresolved += 1
                attempted_unresolved.append(album.id)
                self._events.emit(
                    job="resolution",
                    type="no_match",
                    message=f"No MusicBrainz match for '{album.artist} — {album.title}'",
                    album_id=album.id,
                )
        # Count this pass against the ones that didn't resolve, so the persistent tail sinks in
        # the least-tried-first order and stops crowding out fresh albums next pass.
        self._repo.bump_resolution_attempts(attempted_unresolved)
        if errored:
            log.warning("resolution: %s album(s) failed on upstream errors; will retry", errored)
        return ResolveResult(resolved=resolved, unresolved=unresolved, paused=False)
