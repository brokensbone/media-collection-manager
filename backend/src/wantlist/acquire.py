from dataclasses import dataclass

from .adapters.album_repo import AlbumRepo
from .domain.bandcamp import bandcamp_search_url
from .library_assist import LibraryAssistService, LinkCandidate


@dataclass
class AcquireItem:
    id: int
    artist: str
    title: str
    has_art: bool
    bandcamp_url: str
    possibly_owned: bool  # a same-artist/similar-title edition already sits in beets (§7)
    owned_hint: str | None


class AcquireService:
    """The Acquire worklist (§7): `wanted` albums with a Bandcamp buy link, a "possibly already
    owned?" hint, and marking a want owned — optionally linked to a beets album the operator
    finds via library search (the sticky manual link that keeps the loop closable)."""

    def __init__(self, *, repo: AlbumRepo, assist: LibraryAssistService) -> None:
        self._repo = repo
        self._assist = assist

    def queue(self) -> list[AcquireItem]:
        rows = self._repo.acquire_queue()
        hints = self._assist.owned_hints([(r.id, r.artist, r.title) for r in rows])
        return [
            AcquireItem(
                id=row.id,
                artist=row.artist,
                title=row.title,
                has_art=row.has_art,
                bandcamp_url=bandcamp_search_url(row.artist, row.title),
                possibly_owned=row.id in hints,
                owned_hint=hints[row.id].owned_hint if row.id in hints else None,
            )
            for row in rows
        ]

    def search_library(self, query: str) -> list[LinkCandidate]:
        return self._assist.search(query)

    def mark_owned(self, album_id: int, beets_id: str | None = None) -> None:
        self._repo.mark_owned_manual(album_id, beets_id)
