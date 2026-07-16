from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from wantlist.acquire import AcquireService
from wantlist.adapters.album_repo import AlbumRepo
from wantlist.app import create_app
from wantlist.config import Settings
from wantlist.models import Album, AlbumState, Provenance

from .fakes import FrozenClock

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _client(sf: sessionmaker[Session]) -> tuple[TestClient, AlbumRepo]:
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
    app.state.acquire_service = AcquireService(repo=AlbumRepo(sf), clock=FrozenClock(NOW))
    return TestClient(app), AlbumRepo(sf)


def test_acquire_then_order_clears(clean_album_tables: sessionmaker[Session]) -> None:
    client, repo = _client(clean_album_tables)
    queue = client.get("/acquire").json()
    assert len(queue) == 1
    assert queue[0]["bandcamp_url"].startswith("https://bandcamp.com/search?q=")

    resp = client.post(f"/albums/{queue[0]['id']}/order")
    assert resp.status_code == 204
    assert client.get("/acquire").json() == []
    assert {a.title: a.state for a in repo.list_albums()} == {"Want It": "acquiring"}


def test_mark_owned_endpoint(clean_album_tables: sessionmaker[Session]) -> None:
    client, repo = _client(clean_album_tables)
    album_id = client.get("/acquire").json()[0]["id"]
    resp = client.post(f"/albums/{album_id}/mark-owned")
    assert resp.status_code == 204
    assert {a.title: a.owned for a in repo.list_albums()} == {"Want It": True}
