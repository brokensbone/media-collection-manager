from fastapi.testclient import TestClient

from wantlist.app import create_app
from wantlist.config import Settings


class _TransmissionService:
    def __init__(self) -> None:
        self.added: list[bytes] = []

    def add_torrent(self, metainfo: bytes) -> None:
        self.added.append(metainfo)


def _client() -> tuple[TestClient, _TransmissionService]:
    app = create_app(Settings())
    service = _TransmissionService()
    app.state.transmission_service = service
    return TestClient(app), service


def test_upload_starts_torrent_download() -> None:
    client, service = _client()
    response = client.post(
        "/transmission/torrents",
        files={"file": ("album.torrent", b"d4:infodee", "application/x-bittorrent")},
    )
    assert response.status_code == 200
    assert response.json() == {"detail": "Torrent added to Transmission."}
    assert service.added == [b"d4:infodee"]


def test_upload_rejects_non_torrent_file() -> None:
    client, _ = _client()
    response = client.post("/transmission/torrents", files={"file": ("album.zip", b"zip")})
    assert response.status_code == 400
    assert response.json() == {"detail": "Choose a .torrent file."}
