from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.album_repo import AlbumRepo
from mcm.adapters.beets import BeetsAlbum
from mcm.models import Album, AlbumState, LinkSource, Provenance
from mcm.ports.spotify_api import SavedAlbum
from mcm.reverse_match import ReverseMatcher

from .fakes import StubSpotifyApiClient, StubTokens

FOUND = SavedAlbum(
    spotify_id="sp1",
    artist="Mclusky",
    artist_id=None,
    title="The World (Spotify)",
    upc=None,
    added_at=None,
    art_url="http://art/mclusky.jpg",
)


def _matcher(
    sf: sessionmaker[Session], *, search: dict[str, SavedAlbum] | None = None, fail: bool = False
) -> ReverseMatcher:
    return ReverseMatcher(
        repo=AlbumRepo(sf),
        api=StubSpotifyApiClient(search=search or {}),  # type: ignore[arg-type]
        tokens=StubTokens(fail=fail),  # type: ignore[arg-type]
    )


def _only_album(sf: sessionmaker[Session]) -> Album:
    with sf() as session:
        return session.execute(select(Album)).scalar_one()


def test_creates_owned_entry_with_art_when_spotify_finds_it(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    created = _matcher(sf, search={"Mclusky The World": FOUND}).claim(
        [BeetsAlbum("b1", "Mclusky", "The World", "rg1")]
    )
    assert len(created) == 1
    row = _only_album(sf)
    assert row.state == AlbumState.owned
    assert row.provenance == Provenance.manual
    assert row.owned_link_source == LinkSource.manual
    assert row.owned_beets_id == "b1"
    assert row.mb_releasegroup_id == "rg1"
    assert (row.artist, row.title) == ("Mclusky", "The World")  # beets tags, not the Spotify title
    assert row.spotify_id == "sp1"  # ...but enriched with the Spotify id + art
    assert row.art_url == "http://art/mclusky.jpg"


def test_creates_owned_entry_from_tags_when_no_spotify_match(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    created = _matcher(sf, search={}).claim([BeetsAlbum("b1", "Obscure", "Tape", "rg9")])
    assert len(created) == 1
    row = _only_album(sf)
    assert row.state == AlbumState.owned
    assert (row.artist, row.title) == ("Obscure", "Tape")
    assert row.spotify_id is None
    assert row.art_url is None


def test_still_records_when_spotify_reauth_required(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    created = _matcher(sf, fail=True).claim([BeetsAlbum("b1", "A", "B", "rg1")])
    assert len(created) == 1
    assert _only_album(sf).spotify_id is None  # no token → no enrichment, still owned


def test_skips_album_whose_release_group_a_want_already_covers(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    with sf() as session:  # an existing want already resolved to rg1
        session.add(
            Album(
                spotify_id="existing",
                artist="Mclusky",
                title="The World",
                mb_releasegroup_id="rg1",
                state=AlbumState.wanted,
                provenance=Provenance.spotify_save,
            )
        )
        session.commit()

    created = _matcher(sf, search={"Mclusky The World": FOUND}).claim(
        [BeetsAlbum("b1", "Mclusky", "The World", "rg1")]
    )
    assert created == []  # reconcile will own the existing want; don't duplicate
    assert len(AlbumRepo(sf).list_albums()) == 1
