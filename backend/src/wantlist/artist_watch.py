import logging
from dataclasses import dataclass

from .adapters.album_repo import AlbumRepo
from .ports.spotify import AccessTokenProvider, ReauthRequired
from .ports.spotify_api import SpotifyApiClient

log = logging.getLogger(__name__)


@dataclass
class WatchResult:
    added: int
    artists: int
    paused: bool


class ArtistWatchService:
    """Surface new releases from watched artists as `suggested` (SPEC §6b). Seed = followed
    artists ∪ artists of kept albums. Deduped against everything already known."""

    def __init__(
        self, *, api: SpotifyApiClient, repo: AlbumRepo, tokens: AccessTokenProvider
    ) -> None:
        self._api = api
        self._repo = repo
        self._tokens = tokens

    def poll(self) -> WatchResult:
        try:
            token = self._tokens.valid_access_token()
        except ReauthRequired:
            log.warning("Spotify re-auth required; skipping artist watch")
            return WatchResult(added=0, artists=0, paused=True)

        artist_ids = set(self._api.followed_artist_ids(token)) | self._repo.kept_artist_ids()
        existing = self._repo.existing_spotify_ids()
        added = 0
        for artist_id in artist_ids:
            for album in self._api.artist_albums(token, artist_id):
                if album.spotify_id in existing:
                    continue
                self._repo.add_suggested_album(
                    spotify_id=album.spotify_id,
                    artist=album.artist,
                    artist_id=album.artist_id,
                    title=album.title,
                    art_url=album.art_url,
                )
                existing.add(album.spotify_id)
                added += 1
        return WatchResult(added=added, artists=len(artist_ids), paused=False)
