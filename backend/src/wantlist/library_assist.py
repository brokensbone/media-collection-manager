from dataclasses import dataclass
from typing import Protocol

from .adapters.album_repo import AlbumRepo
from .adapters.beets import BeetsAlbum
from .domain.match import Candidate, edition_match, token_search

_SEARCH_LIMIT = 8


class LibraryCatalog(Protocol):
    def all_albums(self) -> list[BeetsAlbum]: ...


@dataclass
class LinkCandidate:
    beets_id: str
    artist: str
    title: str
    has_release_group: bool


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

    def search(self, query: str) -> list[LinkCandidate]:
        """Rank the beets library against a free-text query (the Mark-owned search box), so the
        operator can find the exact album to link. Empty query returns nothing."""
        if not query.strip():
            return []
        albums = self._catalog.all_albums()
        by_id = {a.beets_id: a for a in albums}
        matches = token_search(
            query,
            [Candidate(a.beets_id, a.artist, a.title) for a in albums],
            limit=_SEARCH_LIMIT,
        )
        return [
            LinkCandidate(
                beets_id=c.key,
                artist=c.artist,
                title=c.title,
                has_release_group=by_id[c.key].mb_releasegroup_id is not None,
            )
            for c in matches
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
