from collections.abc import Iterable

from sqlalchemy.orm import Session, sessionmaker

from wantlist.acquire import AcquireService
from wantlist.adapters.album_repo import AlbumRepo
from wantlist.adapters.beets import BeetsAlbum
from wantlist.library_assist import LibraryAssistService
from wantlist.models import Album, AlbumState, Provenance
from wantlist.reconcile import OwnershipReconciler

from .fakes import StubLibraryCatalog, StubOwnedReleaseGroups


def _add(
    sf: sessionmaker[Session],
    *,
    title: str,
    state: AlbumState,
    rgid: str | None = None,
    artist: str = "A",
) -> None:
    with sf() as session:
        session.add(
            Album(
                spotify_id=title,
                artist=artist,
                title=title,
                state=state,
                provenance=Provenance.spotify_save,
                mb_releasegroup_id=rgid,
            )
        )
        session.commit()


def _svc(sf: sessionmaker[Session], catalog: Iterable[BeetsAlbum] = ()) -> AcquireService:
    assist = LibraryAssistService(repo=AlbumRepo(sf), catalog=StubLibraryCatalog(catalog))
    return AcquireService(repo=AlbumRepo(sf), assist=assist)


def _id(sf: sessionmaker[Session], title: str) -> int:
    return next(a.id for a in AlbumRepo(sf).list_albums() if a.title == title)


def test_queue_lists_only_wanted_with_bandcamp_link(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="want-it", state=AlbumState.wanted)
    _add(sf, title="still-saved", state=AlbumState.saved)
    _add(sf, title="already-owned", state=AlbumState.owned)
    queue = _svc(sf).queue()
    assert [i.title for i in queue] == ["want-it"]
    assert queue[0].bandcamp_url.startswith("https://bandcamp.com/search?q=")


def test_mark_owned_survives_reconcile(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _add(sf, title="deluxe-i-own", state=AlbumState.wanted, rgid="rg-standard")
    _svc(sf).mark_owned(_id(sf, "deluxe-i-own"))
    # beets doesn't know rg-standard, but the manual link must stay owned
    OwnershipReconciler(beets=StubOwnedReleaseGroups(set()), repo=AlbumRepo(sf)).reconcile()
    assert {a.title: a.owned for a in AlbumRepo(sf).list_albums()} == {"deluxe-i-own": True}


def test_reconcile_promotes_wanted_to_owned(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="bought", state=AlbumState.wanted, rgid="rg-1")
    # once the files land in beets, reconcile flips the want to owned (no separate order step)
    OwnershipReconciler(beets=StubOwnedReleaseGroups({"rg-1"}), repo=AlbumRepo(sf)).reconcile()
    assert {a.title: a.owned for a in AlbumRepo(sf).list_albums()} == {"bought": True}


def test_queue_flags_possibly_already_owned(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _add(sf, title="Lupercalia", state=AlbumState.wanted, artist="Patrick Wolf")
    _add(sf, title="Obscure Thing", state=AlbumState.wanted, artist="Nobody")
    # beets holds a deluxe edition of Lupercalia (different/no rgid → the join missed it)
    catalog = [BeetsAlbum("42", "Patrick Wolf", "Lupercalia (Deluxe)", None)]

    by_title = {i.title: i for i in _svc(sf, catalog).queue()}
    assert by_title["Lupercalia"].possibly_owned is True
    assert by_title["Lupercalia"].owned_hint == "Patrick Wolf — Lupercalia (Deluxe)"
    assert by_title["Obscure Thing"].possibly_owned is False


def test_search_library_ranks_matches(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    catalog = [
        BeetsAlbum("1", "Patrick Wolf", "Lupercalia", "rg-x"),
        BeetsAlbum("2", "Someone Else", "Totally Different", None),
    ]
    candidates = _svc(sf, catalog).search_library("patrick wolf lupercalia")

    assert candidates[0].beets_id == "1"  # best match first
    assert candidates[0].has_release_group is True
    assert "2" not in [c.beets_id for c in candidates]  # unrelated album filtered out


def test_search_library_partial_query_finds_album(
    clean_album_tables: sessionmaker[Session],
) -> None:
    # A short query (one word of a long title) must still find the album — the old fuzzy-ratio
    # search scored "mclusky" against "mclusky — The World Loves Us…" below any useful floor.
    sf = clean_album_tables
    catalog = [
        BeetsAlbum("1", "mclusky", "The World Loves Us and Is Our Bitch", "rg-x"),
        BeetsAlbum("2", "Someone Else", "Totally Different", None),
    ]
    candidates = _svc(sf, catalog).search_library("mclusky")
    assert [c.beets_id for c in candidates] == ["1"]


def test_search_library_empty_query_returns_nothing(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    catalog = [BeetsAlbum("1", "Patrick Wolf", "Lupercalia", "rg-x")]
    assert _svc(sf, catalog).search_library("  ") == []
