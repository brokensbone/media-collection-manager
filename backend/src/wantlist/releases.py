from .adapters.album_repo import AlbumRepo, SuggestedRow
from .models import AlbumState
from .ports.clock import Clock
from .ports.spotify import AccessTokenProvider
from .ports.spotify_api import SpotifyApiClient


class ReleasesService:
    """The Releases worklist (§6b/§8d): triage suggested new releases. Save and Want write
    the album to the Spotify library (`user-library-modify`) so `saved` keeps meaning
    'in my library'; Want then jumps straight to `wanted`."""

    def __init__(
        self,
        *,
        api: SpotifyApiClient,
        repo: AlbumRepo,
        tokens: AccessTokenProvider,
        clock: Clock,
    ) -> None:
        self._api = api
        self._repo = repo
        self._tokens = tokens
        self._clock = clock

    def queue(self) -> list[SuggestedRow]:
        return self._repo.suggested_queue()

    def save(self, album_id: int) -> None:
        self._save_to_spotify(album_id)
        self._repo.transition_suggested(
            album_id, AlbumState.saved, saved_at=self._clock.now(), verdict_at=None
        )

    def want(self, album_id: int) -> None:
        self._save_to_spotify(album_id)
        now = self._clock.now()
        self._repo.transition_suggested(album_id, AlbumState.wanted, saved_at=now, verdict_at=now)

    def dismiss(self, album_id: int) -> None:
        self._repo.transition_suggested(
            album_id, AlbumState.dismissed, saved_at=None, verdict_at=self._clock.now()
        )

    def _save_to_spotify(self, album_id: int) -> None:
        spotify_id = self._repo.spotify_id_of(album_id)
        if spotify_id:
            self._api.save_album(self._tokens.valid_access_token(), spotify_id)
