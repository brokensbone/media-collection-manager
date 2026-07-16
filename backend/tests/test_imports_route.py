from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.app import create_app
from wantlist.config import Settings
from wantlist.imports import ImportRunner, ImportsService

from .fakes import FakeFileTransfer, RecordingBeetsClient


def test_import_queue_then_one_click_import(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    download_dir = tmp_path / "Album"
    download_dir.mkdir()
    (download_dir / "01.flac").write_text("track")
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    repo = AlbumRepo(sf)
    repo.add_download_import(
        torrent_hash="h1",
        name="Album",
        download_dir=str(download_dir),
        files=["01.flac"],
        matched_album_id=None,
    )

    beets = RecordingBeetsClient()
    app = create_app(Settings())
    app.state.imports_service = ImportsService(
        repo=repo,
        runner=ImportRunner(repo=repo, transfer=FakeFileTransfer(), beets=beets, inbox=str(inbox)),
    )
    client = TestClient(app)

    queue = client.get("/imports").json()
    assert len(queue) == 1
    import_id = queue[0]["id"]

    resp = client.post(f"/imports/{import_id}/import")
    assert resp.status_code == 204
    assert len(beets.imported) == 1
    assert client.get("/imports").json() == []
    assert (download_dir / "01.flac").read_text() == "track"  # seedbox source untouched
