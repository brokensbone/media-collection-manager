from fastapi.testclient import TestClient

from mcm.app import create_app
from mcm.config import Settings
from mcm.ports.transmission import AddedTorrent


class _TorrentSubmissionService:
    def __init__(self, already_present: list[bool] | None = None) -> None:
        self.added: list[bytes] = []
        self.already_present = already_present or []

    def submit(self, metainfo: bytes) -> AddedTorrent:
        self.added.append(metainfo)
        i = len(self.added) - 1
        dup = self.already_present[i] if i < len(self.already_present) else False
        return AddedTorrent(name=f"t{i}", hash=f"h{i}", already_present=dup)


def _client(
    already_present: list[bool] | None = None,
) -> tuple[TestClient, _TorrentSubmissionService]:
    app = create_app(Settings())
    service = _TorrentSubmissionService(already_present)
    app.state.torrent_submission_service = service
    return TestClient(app), service


def _upload(client: TestClient, n: int) -> dict:
    return client.post(
        "/transmission/torrents",
        files=[
            ("files", (f"f{i}.torrent", f"f{i}".encode(), "application/x-bittorrent"))
            for i in range(n)
        ],
    ).json()


def test_upload_starts_torrent_downloads() -> None:
    client, service = _client()
    response = client.post(
        "/transmission/torrents",
        files=[
            ("files", ("first.torrent", b"first", "application/x-bittorrent")),
            ("files", ("second.torrent", b"second", "application/x-bittorrent")),
        ],
    )
    assert response.status_code == 200
    assert response.json() == {"detail": "2 torrents added to Transmission."}
    assert service.added == [b"first", b"second"]


def test_upload_rejects_non_torrent_file() -> None:
    client, _ = _client()
    response = client.post("/transmission/torrents", files={"files": ("album.zip", b"zip")})
    assert response.status_code == 400
    assert response.json() == {"detail": "Choose .torrent files only."}


def test_a_torrent_transmission_already_had_is_counted_separately() -> None:
    # The bug: five files chosen, five reported added, one of which started nothing.
    client, _ = _client(already_present=[False, False, False, False, True])
    assert _upload(client, 5) == {
        "detail": "4 torrents added to Transmission; 1 was already there."
    }


def test_all_duplicates_says_nothing_started() -> None:
    client, _ = _client(already_present=[True, True])
    assert _upload(client, 2) == {"detail": "2 torrents were already in Transmission."}


def test_a_single_duplicate_reads_naturally() -> None:
    client, _ = _client(already_present=[True])
    assert _upload(client, 1) == {"detail": "1 torrent was already in Transmission."}


def test_several_duplicates_alongside_new_ones() -> None:
    client, _ = _client(already_present=[True, False, True])
    assert _upload(client, 3) == {
        "detail": "1 torrent added to Transmission; 2 were already there."
    }
