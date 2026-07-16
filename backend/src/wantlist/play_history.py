import logging
from dataclasses import dataclass

from .adapters.album_repo import AlbumRepo
from .ports.spotify import AccessTokenProvider, ReauthRequired
from .ports.spotify_api import SpotifyApiClient

log = logging.getLogger(__name__)


@dataclass
class PollResult:
    added: int
    paused: bool


class PlayHistoryService:
    """Accumulate a local scrobble log by polling recently-played (SPEC §4a)."""

    def __init__(
        self, *, api: SpotifyApiClient, repo: AlbumRepo, tokens: AccessTokenProvider
    ) -> None:
        self._api = api
        self._repo = repo
        self._tokens = tokens

    def poll(self) -> PollResult:
        try:
            token = self._tokens.valid_access_token()
        except ReauthRequired:
            log.warning("Spotify re-auth required; skipping play-history poll")
            return PollResult(added=0, paused=True)
        added = self._repo.add_plays(self._api.recently_played(token))
        return PollResult(added=added, paused=False)
