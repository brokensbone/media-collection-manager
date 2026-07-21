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


@dataclass
class OwnedAlbum:
    beets_id: str
    artist: str
    title: str
    mb_releasegroup_id: str | None
    album_id: int | None  # matched tracked album, for its cover art (None = unmatched)
    has_art: bool
    on_spotify: bool  # also present in your Spotify saves/library


class LibraryAssistService:
    """D17 assisted tail (§5/§7): match a want against the beets library so linking is one
    click, and flag wants that look already-owned (a different edition the rgid join missed).
    Also serves the Owned view: the beets library *is* what you own, overlaid with Spotify."""

    def __init__(self, *, repo: AlbumRepo, catalog: LibraryCatalog) -> None:
        self._repo = repo
        self._catalog = catalog

    def owned_library(self) -> list[OwnedAlbum]:
        """The Owned view: the whole beets catalogue (what you actually own), enriched from the
        DB where a release-group matches — cover art and whether it's also in your Spotify saves.
        beets is the source of truth for ownership; Spotify is overlaid where it lines up."""
        enrichment = self._repo.enrichment_by_release_group()
        owned: list[OwnedAlbum] = []
        for a in self._catalog.all_albums():
            match = enrichment.get(a.mb_releasegroup_id) if a.mb_releasegroup_id else None
            owned.append(
                OwnedAlbum(
                    beets_id=a.beets_id,
                    artist=a.artist,
                    title=a.title,
                    mb_releasegroup_id=a.mb_releasegroup_id,
                    album_id=match.album_id if match else None,
                    has_art=match.has_art if match else False,
                    on_spotify=match.on_spotify if match else False,
                )
            )
        owned.sort(key=lambda o: (o.artist.lower(), o.title.lower()))
        return owned

    def owned_count(self) -> int:
        """Size of the beets library — the Owned dashboard tile."""
        return len(self._catalog.all_albums())

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
