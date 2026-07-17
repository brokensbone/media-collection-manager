from dataclasses import dataclass
from typing import Protocol

from .adapters.album_repo import AlbumRepo
from .adapters.beets import BeetsAlbum
from .domain.match import Candidate, edition_match, rank

# Fuzzy is safe for candidates (a human confirms the pick), so the floor is generous. The
# "possibly already owned?" hint fires unprompted, so it uses strict token containment.
_CANDIDATE_FLOOR = 0.3
_CANDIDATE_LIMIT = 5


class LibraryCatalog(Protocol):
    def all_albums(self) -> list[BeetsAlbum]: ...


@dataclass
class LinkCandidate:
    beets_id: str
    artist: str
    title: str
    has_release_group: bool
    score: float


@dataclass
class OwnedHint:
    possibly_owned: bool
    owned_hint: str | None  # "Artist — Title" of the likely-owned edition, for display


class LibraryAssistService:
    """D17 assisted tail (§5/§7): match a want against the beets library so linking is one
    click, and flag wants that look already-owned (a different edition the rgid join missed)."""

    def __init__(self, *, repo: AlbumRepo, catalog: LibraryCatalog) -> None:
        self._repo = repo
        self._catalog = catalog

    def link_candidates(self, album_id: int) -> list[LinkCandidate]:
        want = self._repo.album_artist_title(album_id)
        if want is None:
            return []
        albums = self._catalog.all_albums()
        by_id = {a.beets_id: a for a in albums}
        ranked = rank(
            f"{want[0]} {want[1]}",
            [Candidate(a.beets_id, a.artist, a.title) for a in albums],
            limit=_CANDIDATE_LIMIT,
            floor=_CANDIDATE_FLOOR,
        )
        return [
            LinkCandidate(
                beets_id=c.key,
                artist=c.artist,
                title=c.title,
                has_release_group=by_id[c.key].mb_releasegroup_id is not None,
                score=round(score, 3),
            )
            for c, score in ranked
        ]

    def owned_hints(self, wants: list[tuple[int, str, str]]) -> dict[int, OwnedHint]:
        """Best-effort per-want "possibly already owned?" flags for the Acquire queue. One
        beets dump for the whole queue; a beets hiccup yields no hints rather than failing."""
        try:
            albums = self._catalog.all_albums()
        except Exception:
            return {}
        candidates = [Candidate(a.beets_id, a.artist, a.title) for a in albums]
        hints: dict[int, OwnedHint] = {}
        for album_id, artist, title in wants:
            c = edition_match(f"{artist} {title}", candidates)
            if c is not None:
                hints[album_id] = OwnedHint(
                    possibly_owned=True, owned_hint=f"{c.artist} — {c.title}"
                )
        return hints
