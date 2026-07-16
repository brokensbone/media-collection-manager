from dataclasses import dataclass
from datetime import timedelta

from .adapters.album_repo import AlbumRepo
from .domain.verdict import forgotten_reason
from .models import AlbumState
from .ports.clock import Clock


@dataclass
class DecideItem:
    id: int
    artist: str
    title: str
    reason: str
    has_art: bool


class DecideService:
    """The Decide worklist (§6a/§8d): surface saved albums ready to judge, and record the
    keep/drop/snooze verdicts. v1 uses only the time-based 'forgotten' trigger."""

    def __init__(self, *, repo: AlbumRepo, clock: Clock, forgotten_days: int, snooze_days: int):
        self._repo = repo
        self._clock = clock
        self._forgotten_days = forgotten_days
        self._snooze_days = snooze_days

    def queue(self) -> list[DecideItem]:
        now = self._clock.now()
        cutoff = now - timedelta(days=self._forgotten_days)
        return [
            DecideItem(
                id=row.id,
                artist=row.artist,
                title=row.title,
                reason=forgotten_reason(row.saved_at, now),
                has_art=row.has_art,
            )
            for row in self._repo.decide_queue(cutoff, now)
        ]

    def keep(self, album_id: int) -> None:
        self._repo.set_verdict(album_id, AlbumState.wanted, self._clock.now())

    def drop(self, album_id: int) -> None:
        self._repo.set_verdict(album_id, AlbumState.dismissed, self._clock.now())

    def snooze(self, album_id: int) -> None:
        self._repo.snooze(album_id, self._clock.now() + timedelta(days=self._snooze_days))
