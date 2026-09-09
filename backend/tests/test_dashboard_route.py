from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mcm.acquire import AcquireService
from mcm.adapters.album_repo import AlbumRepo
from mcm.adapters.beets import BeetsAlbum
from mcm.app import create_app
from mcm.config import Settings
from mcm.decide import DecideService
from mcm.library_assist import LibraryAssistService
from mcm.models import Album, AlbumState, Provenance

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
        snooze_days=14,
        listened_tracks=4,
        listened_days=3,
    )
    app.state.acquire_service = AcquireService(
        repo=AlbumRepo(sf),
        assist=LibraryAssistService(repo=AlbumRepo(sf), catalog=StubLibraryCatalog()),
    )
    # Owned is now the beets library size, not the DB `owned` state — three albums in beets even
    # though only one DB row is in the `owned` state.
    library = [BeetsAlbum(str(i), "A", f"lib-{i}", None) for i in range(3)]
    app.state.library_assist_service = LibraryAssistService(
        repo=AlbumRepo(sf), catalog=StubLibraryCatalog(library)
    )

    body = TestClient(app).get("/dashboard").json()
    assert body == {
        "releases": 0,
        "decide": 1,
        "acquire": 2,
        "import": 0,  # nothing awaiting an Import decision
        "tasks": 0,  # nothing queued/importing/failed
        "owned": 3,
        "dismissed": 0,
        "resolved": 0,  # none of these have a release-group yet
        "unresolved": 4,  # all four non-dismissed albums await resolution
    }
