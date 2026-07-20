import subprocess

from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.models import ImportSource, ImportState
from wantlist.transmission_service import TransmissionService


class _OkClient:
    def ping(self) -> None:
        return None


class _BoomClient:
    def ping(self) -> None:
        raise ConnectionError("connection refused")


class _OkTransfer:
    def test(self) -> None:
        return None


class _BoomTransfer:
    def test(self) -> None:
        raise subprocess.CalledProcessError(255, "ssh", stderr="Permission denied (publickey).")


def _svc(
    sf: sessionmaker[Session],
    *,
    client: object | None = None,
    transfer: object | None = None,
    api: bool = True,
    ssh: bool = True,
) -> TransmissionService:
    return TransmissionService(
        repo=AlbumRepo(sf),
        client=client or _OkClient(),  # type: ignore[arg-type]
        transfer=transfer or _OkTransfer(),  # type: ignore[arg-type]
        api_configured=api,
        ssh_configured=ssh,
    )


def test_test_reports_both_connections_ok(clean_album_tables: sessionmaker[Session]) -> None:
    report = _svc(clean_album_tables).test()
    assert report.api.ok is True
    assert report.ssh.ok is True


def test_test_surfaces_failure_detail(clean_album_tables: sessionmaker[Session]) -> None:
    report = _svc(clean_album_tables, client=_BoomClient(), transfer=_BoomTransfer()).test()
    assert report.api.ok is False and "connection refused" in report.api.detail
    assert report.ssh.ok is False and "Permission denied" in report.ssh.detail


def test_test_reports_not_configured(clean_album_tables: sessionmaker[Session]) -> None:
    report = _svc(clean_album_tables, api=False, ssh=False).test()
    assert report.api.ok is False and "Not configured" in report.api.detail
    assert report.ssh.ok is False and "Not configured" in report.ssh.detail


def test_torrents_lists_all_seen_including_non_music(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    repo = AlbumRepo(sf)
    repo.add_pending_import(
        source=ImportSource.transmission,
        source_key="a",
        name="An Album",
        download_dir="/d",
        files=["01.flac"],
        matched_album_id=None,
        has_audio=True,
    )
    repo.add_pending_import(
        source=ImportSource.transmission,
        source_key="b",
        name="A Movie",
        matched_album_id=None,
        state=ImportState.dismissed,
        has_audio=False,
    )
    # a watch-dir row must not appear on the Transmission page
    repo.add_pending_import(
        source=ImportSource.watchdir,
        source_key="w",
        name="drop.zip",
        archive_path="/w/drop.zip",
        matched_album_id=None,
    )

    rows = {r.name: r for r in _svc(sf).torrents()}
    assert set(rows) == {"An Album", "A Movie"}
    assert rows["An Album"].has_audio is True
    assert rows["A Movie"].has_audio is False  # skipped as non-music, still listed
    assert rows["A Movie"].state == "dismissed"
