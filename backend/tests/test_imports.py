from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.imports import (
    ImportDetectionService,
    ImportRunner,
    ImportsService,
    TransmissionStager,
)
from wantlist.models import Album, AlbumState, ImportSource, ImportState, Provenance
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


def _transmission_runner(repo: AlbumRepo, beets: object, inbox: str) -> ImportRunner:
    return ImportRunner(
        repo=repo,
        stagers={ImportSource.transmission: TransmissionStager(FakeFileTransfer())},
        beets=beets,  # type: ignore[arg-type]
        inbox=inbox,
    )


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
    assert service.poll().detected == 0  # source keys already known → nothing new

    rows = {r.name: r for r in AlbumRepo(sf).list_imports()}
    assert rows["Patrick_Wolf-Lupercalia-2011"].matched_album_id == album_id
    assert rows["Patrick_Wolf-Lupercalia-2011"].state == "detected"
    assert rows["Nothing We Want"].matched_album_id is None  # the no-match tail is still recorded


def test_clicking_import_enqueues_and_worker_processes_it(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    download_dir = tmp_path / "downloads" / "Album"  # the "seedbox" dir with real files
    download_dir.mkdir(parents=True)
    (download_dir / "01.flac").write_text("track one")
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.transmission,
        source_key="h1",
        name="Album",
        download_dir=str(download_dir),
        files=["01.flac"],
        matched_album_id=None,
    )
    service = ImportsService(repo=repo)
    import_id = service.queue()[0].id

    # the "click" only enqueues — the row stays, now marked queued (no blocking import)
    service.enqueue(import_id)
    assert service.queue()[0].state == "queued"
    assert repo.count_active_imports() == 1

    # the worker then processes queued imports in the background
    processed = _transmission_runner(repo, RecordingBeetsClient(), str(inbox)).run_queued()
    assert processed == 1
    assert (download_dir / "01.flac").read_text() == "track one"  # source untouched (§12)
    assert service.queue()[0].state == "imported"  # row persists, now shows success
    assert repo.count_active_imports() == 0


def test_run_marks_failed_and_can_be_retried(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    download_dir = tmp_path / "d"
    download_dir.mkdir()
    (download_dir / "x.flac").write_text("x")
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.transmission,
        source_key="h1",
        name="d",
        download_dir=str(download_dir),
        files=["x.flac"],
        matched_album_id=None,
    )
    import_id = repo.list_imports()[0].id
    repo.queue_import(import_id)

    class BoomBeets:
        def import_dir(self, path: str) -> None:
            raise RuntimeError("beets blew up")

    # run_queued swallows the failure (marks it failed) so a batch isn't blocked
    _transmission_runner(repo, BoomBeets(), str(inbox)).run_queued()
    assert repo.get_pending_import(import_id).state == ImportState.failed.value  # type: ignore[union-attr]
    assert not (inbox / str(import_id)).exists()  # staging still tidied on failure

    # a failed import can be retried (re-queued), then succeeds
    repo.queue_import(import_id)
    _transmission_runner(repo, RecordingBeetsClient(), str(inbox)).run_queued()
    assert repo.get_pending_import(import_id).state == ImportState.imported.value  # type: ignore[union-attr]


def test_run_ignores_not_yet_queued(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.transmission,
        source_key="h1",
        name="d",
        download_dir="/d",
        files=["x.flac"],
        matched_album_id=None,
    )
    import_id = repo.list_imports()[0].id
    beets = RecordingBeetsClient()
    _transmission_runner(repo, beets, str(tmp_path)).run(import_id)  # still 'detected'
    assert beets.imported == []  # nothing imported until it's queued


def test_imports_service_queue_labels_match(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    album_id = _add_wanted(sf, artist="Burial", title="Untrue")
    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.transmission,
        source_key="h1",
        name="Burial-Untrue",
        download_dir="/d",
        files=["a.flac"],
        matched_album_id=album_id,
    )
    repo.add_pending_import(
        source=ImportSource.watchdir,
        source_key="k2",
        name="Mystery.zip",
        archive_path="/w/Mystery.zip",
        matched_album_id=None,
    )

    queue = {i.name: i for i in ImportsService(repo=repo).queue()}
    assert queue["Burial-Untrue"].matched == "Burial — Untrue"
    assert queue["Burial-Untrue"].source == "transmission"
    assert queue["Mystery.zip"].matched is None
    assert queue["Mystery.zip"].source == "watchdir"
