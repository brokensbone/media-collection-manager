from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.app import create_app
from wantlist.config import Settings
from wantlist.decide import DecideService
from wantlist.models import Album, AlbumState, Provenance

from .fakes import FrozenClock

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _client(sf: sessionmaker[Session]) -> tuple[TestClient, AlbumRepo]:
    with sf() as session:
        session.add(
            Album(
                spotify_id="s1",
                artist="A",
                title="Old One",
                state=AlbumState.saved,
                provenance=Provenance.spotify_save,
                saved_at=NOW - timedelta(days=30),
            )
        )
        session.commit()
    app = create_app(Settings())
    app.state.decide_service = DecideService(
        repo=AlbumRepo(sf),
        clock=FrozenClock(NOW),
        forgotten_days=21,
        snooze_days=14,
        listened_tracks=4,
        listened_days=3,
    )
    return TestClient(app), AlbumRepo(sf)


def test_decide_lists_then_keep_clears(clean_album_tables: sessionmaker[Session]) -> None:
    client, repo = _client(clean_album_tables)
    queue = client.get("/decide").json()
    assert len(queue) == 1
    assert queue[0]["reason"] == "30d"

    resp = client.post(f"/albums/{queue[0]['id']}/keep")
    assert resp.status_code == 204
    assert client.get("/decide").json() == []
    assert {a.title: a.state for a in repo.list_albums()} == {"Old One": "wanted"}
