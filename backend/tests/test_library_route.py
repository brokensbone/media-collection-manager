from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.adapters.beets import BeetsAlbum
from wantlist.app import create_app
from wantlist.config import Settings
from wantlist.library_assist import LibraryAssistService
from wantlist.models import Album, AlbumState, Provenance

from .fakes import StubLibraryCatalog


def _client(sf: sessionmaker[Session]) -> TestClient:
    with sf() as session:
        session.add(
            Album(
                spotify_id="s1",
                artist="Zebra",
                title="Owned One",
                state=AlbumState.owned,
                provenance=Provenance.spotify_save,
            )
        )
        session.add(
            Album(
                spotify_id="s2",
                artist="Apple",
                title="Saved One",
                state=AlbumState.saved,
                provenance=Provenance.spotify_save,
            )
        )
        session.commit()
    app = create_app(Settings())
    app.state.album_repo = AlbumRepo(sf)
    return TestClient(app)


def test_albums_listed_ordered_by_artist(clean_album_tables: sessionmaker[Session]) -> None:
    albums = _client(clean_album_tables).get("/albums").json()
    assert [a["artist"] for a in albums] == ["Apple", "Zebra"]
    assert {a["title"]: a["owned"] for a in albums} == {"Saved One": False, "Owned One": True}


def test_albums_filtered_by_state(clean_album_tables: sessionmaker[Session]) -> None:
    owned = _client(clean_album_tables).get("/albums", params={"state": "owned"}).json()
    assert len(owned) == 1
    assert owned[0]["title"] == "Owned One"


def test_owned_lists_the_full_beets_library(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    with sf() as session:
        session.add(
            Album(
                spotify_id="s1",
                artist="A",
                title="Matched",
                state=AlbumState.saved,
                provenance=Provenance.spotify_save,
                mb_releasegroup_id="rg-1",
            )
        )
        session.commit()
    catalog = [BeetsAlbum("b1", "A", "Matched", "rg-1"), BeetsAlbum("b2", "B", "Unmatched", None)]
    app = create_app(Settings())
    app.state.album_repo = AlbumRepo(sf)
    app.state.library_assist_service = LibraryAssistService(
        repo=AlbumRepo(sf), catalog=StubLibraryCatalog(catalog)
    )

    owned = TestClient(app).get("/owned").json()

    assert [o["title"] for o in owned] == ["Matched", "Unmatched"]
    assert owned[0]["on_spotify"] is True and owned[0]["album_id"] is not None
    assert owned[0]["spotify_id"] == "s1"
    assert owned[1]["on_spotify"] is False and owned[1]["album_id"] is None
    assert owned[1]["spotify_id"] is None
