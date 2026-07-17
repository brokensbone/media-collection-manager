from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.app import create_app
from wantlist.config import Settings
from wantlist.imports import ImportsService
from wantlist.models import ImportSource


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

    # the row doesn't vanish — it stays, now queued for the worker to process
    after = client.get("/imports").json()
    assert len(after) == 1
    assert after[0]["state"] == "queued"
