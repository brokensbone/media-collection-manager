import pytest

from mcm.torrent_submission_service import TorrentSubmissionService


class _Uploader:
    def __init__(self) -> None:
        self.added: list[bytes] = []

    def add_torrent(self, metainfo: bytes) -> None:
        self.added.append(metainfo)


def test_submit_hands_the_file_to_transmission() -> None:
    uploader = _Uploader()
    TorrentSubmissionService(uploader=uploader, api_configured=True).submit(b"d4:infodee")
    assert uploader.added == [b"d4:infodee"]


def test_submit_requires_configured_rpc() -> None:
    with pytest.raises(RuntimeError, match="not configured"):
        TorrentSubmissionService(uploader=_Uploader(), api_configured=False).submit(b"d4:infodee")
