from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from wantlist.acquire import AcquireService
from wantlist.adapters.album_repo import AlbumRepo
from wantlist.app import create_app
from wantlist.config import Settings
from wantlist.decide import DecideService
from wantlist.library_assist import LibraryAssistService
from wantlist.models import Album, AlbumState, Provenance

from .fakes import FrozenClock, StubLibraryCatalog

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _add(sf: sessionmaker[Session], title: str, state: AlbumState, saved_days: int = 0) -> None:
    with sf() as session:
        session.add(
            Album(
                spotify_id=title,
                artist="A",
                title=title,
                state=state,
                provenance=Provenance.spotify_save,
                saved_at=NOW - timedelta(days=saved_days),
            )
        )
        session.commit()


def test_dashboard_counts(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _add(sf, "old-save", AlbumState.saved, saved_days=30)  # ready to judge
    _add(sf, "want1", AlbumState.wanted)
    _add(sf, "want2", AlbumState.wanted)
    _add(sf, "have", AlbumState.owned)

    app = create_app(Settings())
    app.state.album_repo = AlbumRepo(sf)
    app.state.decide_service = DecideService(
        repo=AlbumRepo(sf),
        clock=FrozenClock(NOW),
        forgotten_days=21,
        snooze_days=14,
        listened_tracks=4,
        listened_days=3,
    )
    app.state.acquire_service = AcquireService(
        repo=AlbumRepo(sf),
        assist=LibraryAssistService(repo=AlbumRepo(sf), catalog=StubLibraryCatalog()),
    )

    body = TestClient(app).get("/dashboard").json()
    assert body == {
        "releases": 0,
        "decide": 1,
        "acquire": 2,
        "import": 0,
        "owned": 1,
        "dismissed": 0,
    }
