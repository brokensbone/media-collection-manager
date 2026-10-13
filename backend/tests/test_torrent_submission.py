import pytest

from mcm.ports.transmission import AddedTorrent
from mcm.torrent_submission_service import TorrentSubmissionService


class _Uploader:
    def __init__(self, already_present: bool = False, name: str = "Some Album") -> None:
        self.added: list[bytes] = []
        self.already_present = already_present
        self.name = name

    def add_torrent(self, metainfo: bytes) -> AddedTorrent:
        self.added.append(metainfo)
        return AddedTorrent(name=self.name, hash="abc123", already_present=self.already_present)


class _Events:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, str, str]] = []

    def emit(self, *, job: str, type: str, message: str, album_id: int | None = None) -> None:
        self.emitted.append((job, type, message))


def test_submit_hands_the_file_to_transmission() -> None:
    uploader = _Uploader()
    TorrentSubmissionService(uploader=uploader, api_configured=True).submit(b"d4:infodee")
    assert uploader.added == [b"d4:infodee"]


def test_submit_requires_configured_rpc() -> None:
    with pytest.raises(RuntimeError, match="not configured"):
        TorrentSubmissionService(uploader=_Uploader(), api_configured=False).submit(b"d4:infodee")


def test_submit_reports_a_started_download() -> None:
    result = TorrentSubmissionService(uploader=_Uploader(), api_configured=True).submit(b"x")
    assert result.already_present is False
    assert result.name == "Some Album"


def test_submit_reports_one_transmission_already_had() -> None:
    uploader = _Uploader(already_present=True)
    result = TorrentSubmissionService(uploader=uploader, api_configured=True).submit(b"x")
    assert result.already_present is True


def test_a_started_download_reaches_the_activity_feed() -> None:
    events = _Events()
    TorrentSubmissionService(uploader=_Uploader(), api_configured=True, events=events).submit(b"x")
    job, kind, message = events.emitted[0]
    assert (job, kind) == ("transmission", "added")
    assert "Some Album" in message


def test_a_duplicate_reaches_the_activity_feed_as_its_own_kind() -> None:
    # Distinguishable in the feed, not just in the response: the feed is where you look
    # later, when the response is long gone.
    events = _Events()
    uploader = _Uploader(already_present=True)
    TorrentSubmissionService(uploader=uploader, api_configured=True, events=events).submit(b"x")
    job, kind, message = events.emitted[0]
    assert (job, kind) == ("transmission", "duplicate")
    assert "Some Album" in message


def test_an_unnamed_torrent_still_logs_something_identifiable() -> None:
    events = _Events()
    uploader = _Uploader(name="")
    TorrentSubmissionService(uploader=uploader, api_configured=True, events=events).submit(b"x")
    assert "abc123" in events.emitted[0][2]
