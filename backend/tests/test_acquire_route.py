from collections.abc import Iterable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mcm.acquire import AcquireService
from mcm.adapters.album_repo import AlbumRepo
from mcm.adapters.beets import BeetsAlbum
from mcm.app import create_app
from mcm.config import Settings
from mcm.library_assist import LibraryAssistService
from mcm.models import Album, AlbumState, Provenance

from .fakes import StubLibraryCatalog


def _client(
    sf: sessionmaker[Session], catalog: Iterable[BeetsAlbum] = ()
) -> tuple[TestClient, AlbumRepo]:
    with sf() as session:
        session.add(
            Album(
                spotify_id="s1",
                artist="A",
                title="Want It",
                state=AlbumState.wanted,
                provenance=Provenance.spotify_save,
            )
        )
        session.commit()
    app = create_app(Settings())
    assist = LibraryAssistService(repo=AlbumRepo(sf), catalog=StubLibraryCatalog(catalog))
    app.state.acquire_service = AcquireService(repo=AlbumRepo(sf), assist=assist)
    return TestClient(app), AlbumRepo(sf)


def test_mark_owned_endpoint(clean_album_tables: sessionmaker[Session]) -> None:
    client, repo = _client(clean_album_tables)
    album_id = client.get("/acquire").json()[0]["id"]
    resp = client.post(f"/albums/{album_id}/mark-owned")
    assert resp.status_code == 204
    assert {a.title: a.owned for a in repo.list_albums()} == {"Want It": True}


def test_search_library_then_mark_owned_with_link(
    clean_album_tables: sessionmaker[Session],
) -> None:
    catalog = [BeetsAlbum("beets-7", "A", "Want It", "rg-9")]
    client, repo = _client(clean_album_tables, catalog)
    album_id = client.get("/acquire").json()[0]["id"]

    candidates = client.get("/library/search", params={"q": "A Want It"}).json()
    assert candidates[0]["beets_id"] == "beets-7"

    resp = client.post(f"/albums/{album_id}/mark-owned", json={"beets_id": "beets-7"})
    assert resp.status_code == 204
    owned = next(a for a in repo.list_albums() if a.id == album_id)
    assert owned.owned is True


def test_return_to_saved_endpoint(clean_album_tables: sessionmaker[Session]) -> None:
    client, repo = _client(clean_album_tables)
    album_id = client.get("/acquire").json()[0]["id"]
    resp = client.post(f"/albums/{album_id}/return-to-saved")
    assert resp.status_code == 204
    assert {a.title: a.state for a in repo.list_albums()} == {"Want It": "saved"}


def test_queue_exposes_possibly_owned(clean_album_tables: sessionmaker[Session]) -> None:
    client, _ = _client(clean_album_tables, [BeetsAlbum("9", "A", "Want It (Remaster)", None)])
    item = client.get("/acquire").json()[0]
    assert item["possibly_owned"] is True
    assert item["owned_hint"] == "A — Want It (Remaster)"
