from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.album_repo import AlbumRepo
from mcm.app import create_app
from mcm.config import Settings
from mcm.imports import ImportsService
from mcm.models import ImportSource, ImportTarget, MediaKind


def test_import_click_enqueues_and_row_persists_with_status(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.watchdir,
        source_key="k1",
        name="Album.zip",
        archive_path="/w/Album.zip",
        matched_album_id=None,
    )

    app = create_app(Settings())
    app.state.imports_service = ImportsService(repo=repo)
    client = TestClient(app)

    queue = client.get("/imports").json()
    assert len(queue) == 1
    assert queue[0]["state"] == "detected"
    import_id = queue[0]["id"]

    resp = client.post(f"/imports/{import_id}/import")
    assert resp.status_code == 204

    # the row leaves the Import worklist (nothing left to decide) and becomes a queued Task
    assert client.get("/imports").json() == []
    tasks = client.get("/imports/tasks").json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == import_id
    assert tasks[0]["state"] == "queued"


def test_scan_imports_forces_watchdir_detection(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    repo = AlbumRepo(sf)

    class FakeWatchdir:
        forced: bool | None = None

        def poll(self, *, force: bool = False):
            self.forced = force
            return {"detected": 1}

    watchdir = FakeWatchdir()
    app = create_app(Settings())
    app.state.imports_service = ImportsService(repo=repo)
    app.state.watchdir_detection_service = watchdir
    client = TestClient(app)

    resp = client.post("/imports/scan")

    assert resp.status_code == 200
    assert resp.json() == {"detected": 1}
    assert watchdir.forced is True


def test_classify_import_updates_its_target(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.watchdir,
        source_key="k1",
        name="Mystery Pack",
        media_kind=MediaKind.unknown,
        import_target=ImportTarget.review,
        archive_path="/w/Mystery Pack",
        files=["disc1.mkv"],
        matched_album_id=None,
    )

    app = create_app(Settings(workspace_root="/workspace"))
    app.state.imports_service = ImportsService(repo=repo)
    client = TestClient(app)
    import_id = client.get("/imports").json()[0]["id"]

    resp = client.post(f"/imports/{import_id}/classify", json={"kind": "workspace"})

    assert resp.status_code == 204
    row = repo.get_pending_import(import_id)
    assert row is not None
    assert row.import_target == ImportTarget.workspace.value
    assert row.destination_path == "/workspace/Mystery Pack"
