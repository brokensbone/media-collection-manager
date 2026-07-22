import zipfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.adapters.tags import MediaFileTagReader
from wantlist.imports import ImportRunner, WatchdirDetectionService, WatchdirStager
from wantlist.models import Album, AlbumState, ImportSource, ImportState, Provenance

from .fakes import FrozenClock, RecordingBeetsClient

SETTLED_NOW = datetime(2030, 1, 1, tzinfo=UTC)  # far future → any real-mtime drop is settled


class FakeTagReader:
    def __init__(self, mapping: dict[str, tuple[str, str]]) -> None:
        self._m = mapping

    def read(self, path: Path) -> tuple[str, str] | None:
        return self._m.get(path.name)


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


def _write_zip(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def _detector(
    sf: sessionmaker[Session], watch: Path, tags: FakeTagReader, now: datetime = SETTLED_NOW
):
    return WatchdirDetectionService(
        repo=AlbumRepo(sf),
        tags=tags,
        clock=FrozenClock(now),
        watch_dir=str(watch),
        archive_subdir="done",
        settle_seconds=60,
        match_threshold=0.5,
    )


def test_watchdir_matches_by_tags_and_dedupes(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    album_id = _add_wanted(sf, artist="Patrick Wolf", title="Lupercalia")
    watch = tmp_path / "watch"
    (watch / "done").mkdir(parents=True)
    _write_zip(watch / "pw_lup_2011.zip", {"a.flac": "x"})  # unhelpful name; tags carry the match
    _write_zip(watch / "unknown.zip", {"b.flac": "y"})
    (watch / "notes.txt").write_text("ignore me")  # non-zip file ignored
    (watch / "done" / "already.zip").write_text("z")  # archived → never re-ingested

    tags = FakeTagReader({"pw_lup_2011.zip": ("Patrick Wolf", "Lupercalia")})
    detector = _detector(sf, watch, tags)

    assert detector.poll().detected == 2
    assert detector.poll().detected == 0  # source keys known → nothing new

    rows = {r.name: r for r in AlbumRepo(sf).list_imports()}
    assert set(rows) == {"pw_lup_2011.zip", "unknown.zip"}
    assert rows["pw_lup_2011.zip"].matched_album_id == album_id  # matched via embedded tags
    assert rows["pw_lup_2011.zip"].source == "watchdir"
    assert rows["unknown.zip"].matched_album_id is None  # no tags, name doesn't match → tail


def test_tag_reader_degrades_on_a_corrupt_zip(tmp_path: Path) -> None:
    # A non-zip named .zip (a partial download, a stray file) must not raise — else it would
    # crash the whole watch-dir poll and block every other import. It falls back to None (name).
    bad = tmp_path / "corrupt.zip"
    bad.write_bytes(b"definitely not a zip")
    assert MediaFileTagReader().read(bad) is None


def test_watchdir_skips_unsettled_drop(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    watch = tmp_path / "watch"
    watch.mkdir()
    drop = watch / "fresh.zip"
    _write_zip(drop, {"a.flac": "x"})
    # clock == the drop's own mtime → within the settle window → skipped
    now = datetime.fromtimestamp(drop.stat().st_mtime, tz=UTC)

    assert _detector(sf, watch, FakeTagReader({}), now=now).poll().detected == 0


def test_watchdir_forced_scan_picks_up_fresh_audio_folder(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    album_id = _add_wanted(sf, artist="Fennesz", title="Endless Summer")
    watch = tmp_path / "watch"
    folder = watch / "fresh-folder"
    folder.mkdir(parents=True)
    (folder / "01.flac").write_text("x")
    (watch / "notes").mkdir()
    (watch / "notes" / "readme.txt").write_text("ignore me")
    now = datetime.fromtimestamp((folder / "01.flac").stat().st_mtime, tz=UTC)

    detector = _detector(
        sf, watch, FakeTagReader({"fresh-folder": ("Fennesz", "Endless Summer")}), now=now
    )

    assert detector.poll(force=True).detected == 1
    rows = {r.name: r for r in AlbumRepo(sf).list_imports()}
    assert set(rows) == {"fresh-folder"}
    assert rows["fresh-folder"].matched_album_id == album_id


def test_watchdir_import_unpacks_and_archives_original(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    watch = tmp_path / "watch"
    watch.mkdir()
    zip_path = watch / "Album.zip"
    _write_zip(zip_path, {"Album/01.flac": "one", "Album/02.flac": "two"})
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.watchdir,
        source_key=f"{zip_path}:1",
        name="Album.zip",
        archive_path=str(zip_path),
        matched_album_id=None,
    )
    import_id = repo.list_imports()[0].id
    repo.queue_import(import_id)

    beets = RecordingBeetsClient()
    runner = ImportRunner(
        repo=repo,
        stagers={
            ImportSource.watchdir: WatchdirStager(
                watch_dir=str(watch), disposition="archive", archive_subdir="done"
            )
        },
        beets=beets,
        inbox=str(inbox),
    )
    runner.run(import_id)

    # unpacked into staging and handed to beets...
    staged = Path(beets.imported[0])
    assert not staged.exists()  # ...then tidied
    # original archived (the drop is ours — §13), not left in the watch root
    assert not zip_path.exists()
    assert (watch / "done" / "Album.zip").exists()
    assert repo.get_pending_import(import_id).state == ImportState.imported.value  # type: ignore[union-attr]


def test_watchdir_import_delete_disposition(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    watch = tmp_path / "watch"
    watch.mkdir()
    zip_path = watch / "Gone.zip"
    _write_zip(zip_path, {"t.flac": "x"})
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.watchdir,
        source_key=f"{zip_path}:1",
        name="Gone.zip",
        archive_path=str(zip_path),
        matched_album_id=None,
    )
    import_id = repo.list_imports()[0].id
    repo.queue_import(import_id)

    ImportRunner(
        repo=repo,
        stagers={
            ImportSource.watchdir: WatchdirStager(
                watch_dir=str(watch), disposition="delete", archive_subdir="done"
            )
        },
        beets=RecordingBeetsClient(),
        inbox=str(inbox),
    ).run(import_id)

    assert not zip_path.exists()
    assert not (watch / "done").exists()  # delete, not archive
