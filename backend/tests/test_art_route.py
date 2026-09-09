from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.album_repo import AlbumRepo
from mcm.app import create_app
from mcm.config import Settings
from mcm.models import Album, AlbumArt, AlbumState, Provenance


def _client_with_art(sf: sessionmaker[Session]) -> tuple[TestClient, int]:
    with sf() as session:
        album = Album(
            spotify_id="a1",
            artist="A",
            title="T",
            state=AlbumState.saved,
            provenance=Provenance.spotify_save,
        )
        session.add(album)
        session.flush()
        album_id = album.id
        session.add(AlbumArt(album_id=album_id, content_type="image/png", image=b"PNGDATA", size=7))
        session.commit()

    app = create_app(Settings())
    app.state.album_repo = AlbumRepo(sf)
    return TestClient(app), album_id


def test_art_served_with_etag(clean_album_tables: sessionmaker[Session]) -> None:
    client, album_id = _client_with_art(clean_album_tables)
    resp = client.get(f"/art/{album_id}")
    assert resp.status_code == 200
    assert resp.content == b"PNGDATA"
    assert resp.headers["content-type"] == "image/png"
    assert "immutable" in resp.headers["cache-control"]
    assert resp.headers["etag"]


def test_art_not_modified_on_matching_etag(clean_album_tables: sessionmaker[Session]) -> None:
    client, album_id = _client_with_art(clean_album_tables)
    etag = client.get(f"/art/{album_id}").headers["etag"]
    resp = client.get(f"/art/{album_id}", headers={"If-None-Match": etag})
    assert resp.status_code == 304


def test_art_missing_returns_404(clean_album_tables: sessionmaker[Session]) -> None:
    client, _ = _client_with_art(clean_album_tables)
    assert client.get("/art/999999").status_code == 404
