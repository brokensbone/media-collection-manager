import logging

from .adapters.album_repo import AlbumRepo
from .adapters.beets import BeetsAlbum
from .ports.spotify import AccessTokenProvider, ReauthRequired
from .ports.spotify_api import SavedAlbum, SpotifyApiClient

log = logging.getLogger(__name__)


class ReverseMatcher:
    """D21: when an album is imported that matched no want, run the funnel backwards — look it
    up on Spotify for a cover + id and record it as owned, so it shows in Owned instead of
    living invisibly in beets. Best-effort: no Spotify match still creates the entry from the
    beets tags (per the operator's choice), just without art."""

    def __init__(
        self, *, repo: AlbumRepo, api: SpotifyApiClient, tokens: AccessTokenProvider
    ) -> None:
        self._repo = repo
        self._api = api
        self._tokens = tokens

    def claim(self, albums: list[BeetsAlbum]) -> int:
        if not albums:
            return 0
        token = self._token()
        tracked = self._repo.tracked_release_group_ids()
        created = 0
        for album in albums:
            if album.mb_releasegroup_id and album.mb_releasegroup_id in tracked:
                continue  # a want already covers this rgid; reconcile owns it
            found = self._search(token, f"{album.artist} {album.title}")
            self._repo.add_owned_import(
                artist=album.artist,
                title=album.title,
                mb_releasegroup_id=album.mb_releasegroup_id,
                beets_id=album.beets_id,
                spotify_id=found.spotify_id if found else None,
                art_url=found.art_url if found else None,
            )
            created += 1
        return created

    def _token(self) -> str | None:
        try:
            return self._tokens.valid_access_token()
        except ReauthRequired:
            return None  # no Spotify → still record from beets tags, without art

    def _search(self, token: str | None, query: str) -> SavedAlbum | None:
        if token is None:
            return None
        try:
            return self._api.search_album(token, query)
        except Exception:
            log.warning("reverse-match: Spotify search failed for %r", query, exc_info=True)
            return None
