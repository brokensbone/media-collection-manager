import logging
from dataclasses import dataclass

from .adapters.album_repo import AlbumRepo
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
    ) -> None:
        self._api = api
        self._resolver = resolver
        self._repo = repo
        self._tokens = tokens

    def resolve_unresolved(self) -> ResolveResult:
        try:
            token = self._tokens.valid_access_token()
        except ReauthRequired:
            log.warning("Spotify re-auth required; skipping resolution")
            return ResolveResult(resolved=0, unresolved=0, paused=True)

        resolved = unresolved = 0
        for album in self._repo.albums_needing_resolution():
            isrcs = self._api.album_isrcs(token, album.spotify_id) if album.spotify_id else []
            rgid = self._resolver.resolve(
                upc=album.upc, isrcs=isrcs, artist=album.artist, title=album.title
            )
            if rgid:
                self._repo.set_release_group(album.id, rgid)
                resolved += 1
            else:
                unresolved += 1
        return ResolveResult(resolved=resolved, unresolved=unresolved, paused=False)
