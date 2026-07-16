from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.app import create_app
from wantlist.config import Settings
from wantlist.models import Album, AlbumState, Provenance


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
