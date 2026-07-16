from dataclasses import dataclass

from .adapters.album_repo import AlbumRepo
from .domain.bandcamp import bandcamp_search_url
from .ports.clock import Clock


@dataclass
class AcquireItem:
    id: int
    artist: str
    title: str
    has_art: bool
    bandcamp_url: str


class AcquireService:
    """The Acquire worklist (§7/§8d): `wanted` albums with buy-assist, plus the ordered and
    manual-owned transitions that keep the loop always closable."""

    def __init__(self, *, repo: AlbumRepo, clock: Clock) -> None:
        self._repo = repo
        self._clock = clock

    def queue(self) -> list[AcquireItem]:
        return [
            AcquireItem(
                id=row.id,
                artist=row.artist,
                title=row.title,
                has_art=row.has_art,
                bandcamp_url=bandcamp_search_url(row.artist, row.title),
            )
            for row in self._repo.acquire_queue()
        ]

    def mark_ordered(self, album_id: int) -> None:
        self._repo.mark_ordered(album_id, self._clock.now())

    def cancel_order(self, album_id: int) -> None:
        self._repo.cancel_order(album_id)

    def mark_owned(self, album_id: int, beets_id: str | None = None) -> None:
        self._repo.mark_owned_manual(album_id, beets_id)
