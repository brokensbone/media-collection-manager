from collections.abc import Iterable

from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.album_repo import AlbumRepo
from mcm.adapters.beets import BeetsAlbum
from mcm.library_assist import LibraryAssistService
from mcm.models import Album, AlbumState, Provenance

from .fakes import StubLibraryCatalog


def _svc(sf: sessionmaker[Session], catalog: Iterable[BeetsAlbum]) -> LibraryAssistService:
    return LibraryAssistService(repo=AlbumRepo(sf), catalog=StubLibraryCatalog(catalog))


def _add(sf: sessionmaker[Session], **kw: object) -> None:
    with sf() as session:
        session.add(Album(provenance=Provenance.spotify_save, **kw))  # type: ignore[arg-type]
        session.commit()


def test_owned_library_is_the_full_beets_catalogue_enriched(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    # A Spotify save lines up with one beets album by release-group; the other beets album has no
    # Spotify counterpart. Both must appear (owned = the library), sorted by artist/title.
    _add(
        sf,
        spotify_id="s1",
        artist="Beak",
        title="Matched",
        state=AlbumState.saved,
        mb_releasegroup_id="rg-1",
    )
    album_id = next(a.id for a in AlbumRepo(sf).list_albums())
    catalog = [
        BeetsAlbum("b2", "Zamrock", "Only In Beets", None),
        BeetsAlbum("b1", "Beak", "Matched", "rg-1"),
    ]

    owned = _svc(sf, catalog).owned_library()

    assert [(o.artist, o.title) for o in owned] == [
        ("Beak", "Matched"),
        ("Zamrock", "Only In Beets"),
    ]
    assert owned[0].album_id == album_id and owned[0].on_spotify is True
    assert owned[0].spotify_id == "s1"  # carried through so the cover can link to Spotify
    assert owned[1].album_id is None and owned[1].on_spotify is False and owned[1].has_art is False
    assert owned[1].spotify_id is None


def test_owned_library_enriches_an_as_is_album_by_beets_id(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    # An as-is album with NO release-group id, linked to a Spotify row directly by beets id
    # (D21 reverse-match). The rgid join can't reach it; the beets-id fallback must.
    _add(
        sf,
        spotify_id="s2",
        artist="A",
        title="As-Is",
        state=AlbumState.owned,
        mb_releasegroup_id=None,
        owned_beets_id="b9",
    )
    album_id = next(a.id for a in AlbumRepo(sf).list_albums())

    owned = _svc(sf, [BeetsAlbum("b9", "A", "As-Is", None)]).owned_library()

    assert owned[0].album_id == album_id
    assert owned[0].on_spotify is True and owned[0].spotify_id == "s2"


def test_owned_library_shows_cover_from_the_matching_album(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(
        sf,
        spotify_id="s1",
        artist="A",
        title="T",
        state=AlbumState.owned,
        mb_releasegroup_id="rg-1",
    )
    repo = AlbumRepo(sf)
    album_id = next(a.id for a in repo.list_albums())
    repo.save_art(album_id, "image/jpeg", b"IMG")

    owned = _svc(sf, [BeetsAlbum("b1", "A", "T", "rg-1")]).owned_library()

    assert owned[0].album_id == album_id and owned[0].has_art is True


def test_owned_count_is_the_catalogue_size(clean_album_tables: sessionmaker[Session]) -> None:
    catalog = [BeetsAlbum("b1", "A", "One", None), BeetsAlbum("b2", "B", "Two", "rg-2")]
    assert _svc(clean_album_tables, catalog).owned_count() == 2


def test_owned_library_carries_beets_facets(clean_album_tables: sessionmaker[Session]) -> None:
    catalog = [
        BeetsAlbum(
            "b1",
            "Burial",
            "Untrue",
            "rg-1",
            year=2007,
            media='12" Vinyl',
            label="Hyperdub",
            country="GB",
            secondary_types="album",
            genre="Dubstep",
        )
    ]
    owned = _svc(clean_album_tables, catalog).owned_library()[0]
    assert (owned.year, owned.media, owned.label, owned.country) == (
        2007,
        '12" Vinyl',
        "Hyperdub",
        "GB",
    )
    assert owned.secondary_types == "album" and owned.genre == "Dubstep"
