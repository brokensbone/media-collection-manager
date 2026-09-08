from dataclasses import dataclass
from datetime import timedelta

from .adapters.album_repo import AlbumRepo
from .domain.verdict import ZERO_PLAYS, listened_reason
from .models import AlbumState
from .ports.clock import Clock


@dataclass
class DecideItem:
    id: int
    artist: str
    title: str
    reason: str
    has_art: bool
    spotify_id: str | None
    album_type: str | None


class DecideService:
    """The Decide worklist (§6a/§8d): surface every saved album that isn't currently snoozed so
    it can be judged, and record the keep/drop/snooze verdicts. New saves drop straight in;
    snooze is the only way to defer one. Each row carries an optional 'listened' hint from play
    history to flag the easy keeps."""

    def __init__(
        self,
        *,
        repo: AlbumRepo,
        clock: Clock,
        snooze_days: int,
        listened_tracks: int,
        listened_days: int,
    ):
        self._repo = repo
        self._clock = clock
        self._snooze_days = snooze_days
        self._listened_tracks = listened_tracks
        self._listened_days = listened_days

    def queue(self) -> list[DecideItem]:
        now = self._clock.now()
        stats = self._repo.play_stats_by_album()
        items: list[DecideItem] = []
        for cand in self._repo.saved_pending(now):
            stat = stats.get(cand.spotify_id) if cand.spotify_id else None
            reason = listened_reason(
                stat=stat or ZERO_PLAYS,
                listened_tracks=self._listened_tracks,
                listened_days=self._listened_days,
            )
            items.append(
                DecideItem(
                    cand.id,
                    cand.artist,
                    cand.title,
                    reason,
                    cand.has_art,
                    cand.spotify_id,
                    cand.album_type,
                )
            )
        return items

    def keep(self, album_id: int) -> None:
        self._repo.set_verdict(album_id, AlbumState.wanted, self._clock.now())

    def drop(self, album_id: int) -> None:
        self._repo.set_verdict(album_id, AlbumState.dismissed, self._clock.now())

    def snooze(self, album_id: int) -> None:
        self._repo.snooze(album_id, self._clock.now() + timedelta(days=self._snooze_days))
