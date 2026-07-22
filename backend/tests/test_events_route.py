from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.event_log import WorkerEventLog
from wantlist.app import create_app
from wantlist.config import Settings


def _client(sf: sessionmaker[Session]) -> TestClient:
    app = create_app(Settings())
    app.state.event_log = WorkerEventLog(sf)
    return TestClient(app)


def test_events_returns_the_feed(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    WorkerEventLog(sf).emit(job="resolution", type="resolved", message="Resolved 'A — B'")
    body = _client(sf).get("/events").json()
    assert body[-1]["job"] == "resolution"
    assert body[-1]["message"] == "Resolved 'A — B'"
    assert body[-1]["type"] == "resolved"


def test_events_after_cursor_returns_only_newer(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    log = WorkerEventLog(sf)
    log.emit(job="j", type="t", message="old")
    client = _client(sf)
    cursor = client.get("/events").json()[-1]["id"]
    log.emit(job="j", type="t", message="new")
    after = client.get("/events", params={"after": cursor}).json()
    assert [e["message"] for e in after] == ["new"]
