from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.imports import ImportDetectionService, ImportRunner, ImportsService
from wantlist.models import Album, AlbumState, ImportState, Provenance
from wantlist.ports.transmission import Torrent

from .fakes import FakeFileTransfer, RecordingBeetsClient, StubTransmissionClient


def _add_wanted(sf: sessionmaker[Session], *, artist: str, title: str) -> int:
    with sf() as session:
        album = Album(
            spotify_id=f"{artist}:{title}",
            artist=artist,
            title=title,
            state=AlbumState.wanted,
            provenance=Provenance.spotify_save,
        )
        session.add(album)
        session.commit()
        return album.id


def test_detection_matches_and_dedupes_by_hash(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    album_id = _add_wanted(sf, artist="Patrick Wolf", title="Lupercalia")
    transmission = StubTransmissionClient(
        [
            Torrent(
                hash="h1", name="Patrick_Wolf-Lupercalia-2011", download_dir="/d", files=["a.flac"]
            ),
            Torrent(hash="h2", name="Nothing We Want", download_dir="/d", files=["b.flac"]),
        ]
    )
    service = ImportDetectionService(
        transmission=transmission, repo=AlbumRepo(sf), match_threshold=0.5
    )

    assert service.poll().detected == 2
    assert service.poll().detected == 0  # hashes already known → nothing new

    rows = {r.name: r for r in AlbumRepo(sf).pending_imports()}
    assert rows["Patrick_Wolf-Lupercalia-2011"].matched_album_id == album_id
    assert rows["Nothing We Want"].matched_album_id is None  # the no-match tail is still recorded


def test_import_runner_copies_leaving_source_untouched_and_tidies(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    # a "seedbox" download dir with real files
    download_dir = tmp_path / "downloads" / "Album"
    download_dir.mkdir(parents=True)
    (download_dir / "01.flac").write_text("track one")
    (download_dir / "02.flac").write_text("track two")
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    repo = AlbumRepo(sf)
    repo.add_download_import(
        torrent_hash="h1",
        name="Album",
        download_dir=str(download_dir),
        files=["01.flac", "02.flac"],
        matched_album_id=None,
    )
    import_id = repo.pending_imports()[0].id

    beets = RecordingBeetsClient()
    ImportRunner(repo=repo, transfer=FakeFileTransfer(), beets=beets, inbox=str(inbox)).run(
        import_id
    )

    # beets was handed the staging copy...
    assert len(beets.imported) == 1
    staged = Path(beets.imported[0])
    # ...seedbox originals are untouched (seeding-safe, §12)...
    assert (download_dir / "01.flac").read_text() == "track one"
    assert (download_dir / "02.flac").read_text() == "track two"
    # ...the staging copy is tidied away...
    assert not staged.exists()
    # ...and the record is marked imported.
    assert repo.pending_imports() == []
    assert repo.get_download_import(import_id).state == ImportState.imported.value


def test_import_runner_marks_failed_and_reraises(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    download_dir = tmp_path / "d"
    download_dir.mkdir()
    (download_dir / "x.flac").write_text("x")
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    repo = AlbumRepo(sf)
    repo.add_download_import(
        torrent_hash="h1",
        name="d",
        download_dir=str(download_dir),
        files=["x.flac"],
        matched_album_id=None,
    )
    import_id = repo.pending_imports()[0].id

    class BoomBeets:
        def import_dir(self, path: str) -> None:
            raise RuntimeError("beets blew up")

    with pytest.raises(RuntimeError, match="beets blew up"):
        ImportRunner(
            repo=repo, transfer=FakeFileTransfer(), beets=BoomBeets(), inbox=str(inbox)
        ).run(import_id)

    assert repo.get_download_import(import_id).state == ImportState.failed.value
    assert not (inbox / str(import_id)).exists()  # staging still tidied on failure


def test_imports_service_queue_labels_match(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    album_id = _add_wanted(sf, artist="Burial", title="Untrue")
    repo = AlbumRepo(sf)
    repo.add_download_import(
        torrent_hash="h1",
        name="Burial-Untrue",
        download_dir="/d",
        files=["a.flac"],
        matched_album_id=album_id,
    )
    repo.add_download_import(
        torrent_hash="h2",
        name="Mystery",
        download_dir="/d",
        files=["b.flac"],
        matched_album_id=None,
    )
    runner = ImportRunner(
        repo=repo, transfer=FakeFileTransfer(), beets=RecordingBeetsClient(), inbox="/x"
    )
    service = ImportsService(repo=repo, runner=runner)

    queue = {i.name: i for i in service.queue()}
    assert queue["Burial-Untrue"].matched == "Burial — Untrue"
    assert queue["Mystery"].matched is None
