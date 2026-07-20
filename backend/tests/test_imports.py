from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.adapters.beets import BeetsAlbum
from wantlist.imports import (
    ImportDetectionService,
    ImportRunner,
    ImportsService,
    TransmissionStager,
)
from wantlist.models import Album, AlbumState, ImportSource, ImportState, Provenance
from wantlist.ports.spotify_api import SavedAlbum
from wantlist.ports.transmission import Torrent
from wantlist.reverse_match import ReverseMatcher

from .fakes import (
    FakeBeetsLibrary,
    FakeFileTransfer,
    RecordingBeetsClient,
    StubSpotifyApiClient,
    StubTokens,
    StubTransmissionClient,
)


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


def _add(sf: sessionmaker[Session], *, artist: str, title: str, state: AlbumState) -> int:
    with sf() as session:
        album = Album(
            spotify_id=f"{artist}:{title}",
            artist=artist,
            title=title,
            state=state,
            provenance=Provenance.spotify_save,
        )
        session.add(album)
        session.commit()
        return album.id


def test_detection_matches_an_album_still_in_decide(
    clean_album_tables: sessionmaker[Session],
) -> None:
    # A drop for an album you haven't triaged yet (still `saved`, i.e. in Decide) should match:
    # reconcile will flip it to owned by release-group anyway, so the label should reflect that.
    sf = clean_album_tables
    album_id = _add(sf, artist="Patrick Wolf", title="Lupercalia", state=AlbumState.saved)
    transmission = StubTransmissionClient(
        [
            Torrent(
                hash="h1", name="Patrick_Wolf-Lupercalia-2011", download_dir="/d", files=["01.flac"]
            )
        ]
    )
    ImportDetectionService(
        transmission=transmission, repo=AlbumRepo(sf), match_threshold=0.5
    ).poll()

    rows = {r.name: r for r in AlbumRepo(sf).list_imports()}
    assert rows["Patrick_Wolf-Lupercalia-2011"].matched_album_id == album_id


def test_detection_matches_an_already_owned_album(
    clean_album_tables: sessionmaker[Session],
) -> None:
    # A drop for an album you already own is a re-download worth flagging — and matching it
    # keeps reverse-match from minting a duplicate owned entry off Spotify.
    sf = clean_album_tables
    album_id = _add(sf, artist="Patrick Wolf", title="Lupercalia", state=AlbumState.owned)
    transmission = StubTransmissionClient(
        [
            Torrent(
                hash="h1", name="Patrick_Wolf-Lupercalia-2011", download_dir="/d", files=["01.flac"]
            )
        ]
    )
    ImportDetectionService(
        transmission=transmission, repo=AlbumRepo(sf), match_threshold=0.5
    ).poll()

    rows = {r.name: r for r in AlbumRepo(sf).list_imports()}
    assert rows["Patrick_Wolf-Lupercalia-2011"].matched_album_id == album_id


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


def test_matched_import_links_owned_even_without_a_release_group(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    # The download was matched to a known album, but beets imported it as-is (no MB release
    # group), so reconcile can never link it. The match itself must flip the album to owned.
    sf = clean_album_tables
    download_dir = tmp_path / "Album"
    download_dir.mkdir()
    (download_dir / "01.flac").write_text("x")
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    repo = AlbumRepo(sf)
    album_id = _add(sf, artist="Pye Corner Audio", title="No Tomorrow", state=AlbumState.saved)
    repo.add_pending_import(
        source=ImportSource.transmission,
        source_key="h1",
        name="Pye Corner Audio - No Tomorrow",
        download_dir=str(download_dir),
        files=["01.flac"],
        matched_album_id=album_id,
    )
    import_id = repo.list_imports()[0].id
    repo.queue_import(import_id)

    # beets gains the album but with NO release-group id (as-is import)
    added = BeetsAlbum("b9", "Pye Corner Audio", "No Tomorrow", None)
    beets = FakeBeetsLibrary(adds_on_import=added)
    ImportRunner(
        repo=repo,
        stagers={ImportSource.transmission: TransmissionStager(FakeFileTransfer())},
        beets=beets,
        inbox=str(inbox),
        catalog=beets,
    ).run(import_id)

    owned = {a.id: a for a in AlbumRepo(sf).list_albums("owned")}
    assert album_id in owned  # linked owned by the match, not by reconcile
    with sf() as session:
        assert session.get(Album, album_id).owned_beets_id == "b9"  # linked to the import


def test_unmatched_import_reverse_matches_to_owned(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    download_dir = tmp_path / "Album"
    download_dir.mkdir()
    (download_dir / "01.flac").write_text("x")
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.transmission,
        source_key="h1",
        name="Mclusky - The World",
        download_dir=str(download_dir),
        files=["01.flac"],
        matched_album_id=None,  # no want → should reverse-match after import
    )
    import_id = repo.list_imports()[0].id
    repo.queue_import(import_id)

    # beets "gains" this album on import; Spotify search finds it for enrichment
    beets = FakeBeetsLibrary(adds_on_import=BeetsAlbum("b1", "Mclusky", "The World", "rg1"))
    found = SavedAlbum("sp1", "Mclusky", None, "The World", None, None, "http://art.jpg")
    reverse = ReverseMatcher(
        repo=repo,
        api=StubSpotifyApiClient(search={"Mclusky The World": found}),  # type: ignore[arg-type]
        tokens=StubTokens(),  # type: ignore[arg-type]
    )
    ImportRunner(
        repo=repo,
        stagers={ImportSource.transmission: TransmissionStager(FakeFileTransfer())},
        beets=beets,
        inbox=str(inbox),
        catalog=beets,
        reverse_matcher=reverse,
    ).run(import_id)

    owned = AlbumRepo(sf).list_albums("owned")
    assert [(a.artist, a.title, a.owned) for a in owned] == [("Mclusky", "The World", True)]


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


def test_queue_flags_watchdir_drop_whose_file_is_gone(
    clean_album_tables: sessionmaker[Session], tmp_path: Path
) -> None:
    sf = clean_album_tables
    repo = AlbumRepo(sf)
    here = tmp_path / "Here.zip"
    here.write_bytes(b"z")
    repo.add_pending_import(
        source=ImportSource.watchdir,
        source_key="k1",
        name="Here.zip",
        archive_path=str(here),
        matched_album_id=None,
    )
    repo.add_pending_import(
        source=ImportSource.watchdir,
        source_key="k2",
        name="Gone.zip",
        archive_path=str(tmp_path / "Gone.zip"),
        matched_album_id=None,
    )
    repo.add_pending_import(
        source=ImportSource.transmission,
        source_key="h1",
        name="Torrent",
        download_dir="/d",
        files=["a"],
        matched_album_id=None,
    )

    queue = {i.name: i for i in ImportsService(repo=repo).queue()}
    assert queue["Here.zip"].missing is False  # file present
    assert queue["Gone.zip"].missing is True  # file removed → offer removal, not import
    assert queue["Torrent"].missing is False  # transmission has no local file to check


def test_discard_hides_the_row_but_keeps_its_source_key(
    clean_album_tables: sessionmaker[Session],
) -> None:
    # Discard must be sticky: the row leaves the list but its source_key stays in the ledger,
    # so a still-present source (a seeding torrent) isn't re-detected on the next poll.
    sf = clean_album_tables
    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.transmission,
        source_key="h1",
        name="Unwanted",
        download_dir="/d",
        files=["a.flac"],
        matched_album_id=None,
    )
    service = ImportsService(repo=repo)
    import_id = service.queue()[0].id
    service.discard(import_id)
    assert service.queue() == []  # hidden from the list
    assert "h1" in repo.known_source_keys()  # still known → won't re-detect


def test_transmission_detection_ignores_non_music_torrents(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    transmission = StubTransmissionClient(
        [
            Torrent(hash="a", name="Some Album", download_dir="/d", files=["01.flac", "cover.jpg"]),
            Torrent(hash="b", name="A Movie 2160p", download_dir="/d", files=["movie.mkv"]),
            Torrent(hash="c", name="Some.App", download_dir="/d", files=["setup.exe"]),
        ]
    )
    ImportDetectionService(
        transmission=transmission, repo=AlbumRepo(sf), match_threshold=0.5
    ).poll()

    names = {r.name for r in AlbumRepo(sf).list_imports()}
    assert names == {"Some Album"}  # only the torrent with audio files surfaced
