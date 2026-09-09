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
        backoff_base_seconds: int = 3600,
        backoff_cap_seconds: int = 604800,
        error_circuit_break: int = 8,
        events: EventSink | None = None,
    ) -> None:
        self._api = api
        self._resolver = resolver
        self._repo = repo
        self._tokens = tokens
        # Cap albums resolved per pass so a cold start (e.g. 1000 fresh saves) chips away at
        # MusicBrainz politely instead of hammering it for ~20 minutes each reconcile.
        self._max_per_run = max_per_run
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_cap_seconds = backoff_cap_seconds
        self._error_circuit_break = error_circuit_break
        self._events = events or NullEventSink()

    def resolve_unresolved(self) -> ResolveResult:
        candidates = self._repo.albums_needing_resolution(
            backoff_base_seconds=self._backoff_base_seconds,
            backoff_cap_seconds=self._backoff_cap_seconds,
        )
        if self._max_per_run is not None:
            candidates = candidates[: self._max_per_run]

        resolved = unresolved = errored = 0
        consecutive_errors = 0
        # Only genuine "no match" results advance the backoff; an upstream error (MB down) must
        # not, or an outage would push every album out to the ~weekly cap and reshuffle the queue.
        no_match_ids: list[int] = []
        for album in candidates:
            try:
                # Per album, not once per pass: MusicBrainz throttling makes a pass take many
                # minutes, long enough to outlive a Spotify access token. valid_access_token()
                # refreshes ~60s before expiry, so no request 401s partway through the batch.
                token = self._tokens.valid_access_token()
            except ReauthRequired:
                log.warning("Spotify re-auth required; pausing resolution")
                self._repo.bump_resolution_attempts(no_match_ids)
                return ResolveResult(resolved=resolved, unresolved=unresolved, paused=True)
            try:
                isrcs = self._api.album_isrcs(token, album.spotify_id) if album.spotify_id else []
                rgid = self._resolver.resolve(
                    upc=album.upc, isrcs=isrcs, artist=album.artist, title=album.title
                )
            except Exception:
                # A flaky upstream (MB 503/down, Spotify hiccup) must not abort the whole pass on
                # the first blip — but if it keeps failing, MB is down: stop hammering it (and the
                # log) and let the next reconcile retry. Errors don't advance the backoff.
                errored += 1
                unresolved += 1
                consecutive_errors += 1
                self._events.emit(
                    job="resolution",
                    type="error",
                    message=f"Couldn't reach MusicBrainz for '{album.artist} — {album.title}'",
                    album_id=album.id,
                )
                if consecutive_errors >= self._error_circuit_break:
                    log.warning(
                        "resolution: MusicBrainz unreachable (%s consecutive errors); "
                        "aborting pass, will retry next reconcile",
                        consecutive_errors,
                    )
                    break
                continue
            consecutive_errors = 0
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
                no_match_ids.append(album.id)
                self._events.emit(
                    job="resolution",
                    type="no_match",
                    message=f"No MusicBrainz match for '{album.artist} — {album.title}'",
                    album_id=album.id,
                )
        # Advance the backoff for the ones MB actively reported no match for, so the persistent
        # tail sinks in the least-tried order and waits longer before its next attempt.
        self._repo.bump_resolution_attempts(no_match_ids)
        if errored:
            log.warning("resolution: %s album(s) failed on upstream errors; will retry", errored)
        return ResolveResult(resolved=resolved, unresolved=unresolved, paused=False)
