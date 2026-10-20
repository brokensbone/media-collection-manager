from datetime import date
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.beets import BeetsAlbum, BeetsTrack
from mcm.adapters.beets_cache import BeetsCatalogCache
from mcm.adapters.navidrome import NavidromeClient, NavidromeError, relative_path
from mcm.app import create_app
from mcm.config import Settings
from mcm.navidrome_sync import NavidromeSyncService
from mcm.radio_schedules import (
    RadioScheduleService,
    ScheduleInput,
    ScheduleItemInput,
    ScheduleSessionInput,
)
from mcm.worker import build_scheduler

DAY = date(2026, 10, 19)
ROOT = "/radio/schedules/2026-10-19/navidrome"


class Server:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, list[str]]]] = []
        self.songs = [
            {"id": "a", "path": "/music/A/one.flac"},
            {"id": "b", "path": "/music/A/two.flac"},
        ]
        self.playlist: list[str] = []
        self.exists = False
        self.fail = False
        self.lose_create_response = False
        self.corrupt_readback = False
        self.public = False
        self.fail_sharing = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["User-Agent"] == "MCM/1"
        assert not request.url.query  # credentials and song lists must stay out of logs
        params = parse_qs(request.content.decode(), keep_blank_values=True)
        assert params["apiKey"] == ["secret"]
        assert "u" not in params
        endpoint = request.url.path.rsplit("/", 1)[-1]
        self.calls.append((endpoint, params))
        if self.fail:
            return httpx.Response(
                200,
                json={
                    "subsonic-response": {
                        "status": "failed",
                        "error": {"code": 40, "message": "secret"},
                    }
                },
            )
        result: dict[str, object] = {"status": "ok"}
        if endpoint == "search3":
            # Deliberately cap pages below the requested size.
            offset = int(params["songOffset"][0])
            result["searchResult3"] = {"song": self.songs[offset : offset + 1]}
        elif endpoint == "getPlaylists":
            result["playlists"] = {
                "playlist": [{"id": "p1", "name": "MCM Radio — 2026-10-19"}] if self.exists else []
            }
        elif endpoint == "createPlaylist":
            if self.exists:
                assert params["playlistId"] == ["p1"]
            else:
                assert params["name"] == ["MCM Radio — 2026-10-19"]
            self.exists = True
            self.playlist = params.get("songId", [])
            if self.lose_create_response:
                self.lose_create_response = False
                raise httpx.ReadTimeout("secret", request=request)
            result["playlist"] = {"id": "p1"}
        elif endpoint == "updatePlaylist":
            assert params["playlistId"] == ["p1"]
            assert params["public"] == ["true"]
            if self.fail_sharing:
                return httpx.Response(
                    200,
                    json={"subsonic-response": {"status": "failed", "error": {"code": 50}}},
                )
            self.public = True
        elif endpoint == "getPlaylist":
            result["playlist"] = {
                "public": self.public,
                "entry": [
                    {"id": song} for song in ([] if self.corrupt_readback else self.playlist)
                ],
            }
        else:
            raise AssertionError(endpoint)
        return httpx.Response(200, json={"subsonic-response": result})

    def client(self) -> NavidromeClient:
        return NavidromeClient(
            Settings(
                navidrome_url="https://nd.example",
                navidrome_api_key="secret",
                navidrome_path_prefix="/music",
            ),
            httpx.Client(transport=httpx.MockTransport(self.handle)),
        )


def programme(sf: sessionmaker[Session], reverse: bool = False) -> None:
    BeetsCatalogCache(sf).replace(
        [BeetsAlbum("1", "A", "Album", None)],
        [
            BeetsTrack("1", "11", 1, 1, "One", 100, "A/one.flac"),
            BeetsTrack("1", "12", 1, 2, "Two", 100, "A/two.flac"),
        ],
    )
    RadioScheduleService(sf).replace(
        DAY,
        ScheduleInput(
            None,
            [
                ScheduleSessionInput(
                    "track_hour",
                    "Morning",
                    "09:00",
                    None,
                    [
                        ScheduleItemInput("track", None, item)
                        for item in (["12", "11"] if reverse else ["11", "12", "11"])
                    ],
                )
            ],
        ),
    )


def test_opt_in_edit_retry_disable_and_reenable(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    programme(sf)
    service = NavidromeSyncService(sf)
    server = Server()
    client = server.client()
    app = create_app(Settings())
    app.state.navidrome_sync_service = service
    api = TestClient(app)
    assert api.get(ROOT).json()["enabled"] is False
    service.sync_pending(client)
    assert server.calls == []
    assert api.put(ROOT, json={"enabled": True}).status_code == 202
    service.sync_pending(client)
    assert server.playlist == ["a", "b", "a"]
    assert server.public
    status = api.get(ROOT).json()
    assert status["status"] == "synced" and status["playlist_id"] == "p1"
    assert status["track_count"] == 3 and status["last_synced_at"]
    count = len(server.calls)
    service.sync_pending(client)
    assert len(server.calls) == count
    programme(sf, reverse=True)
    assert api.get(ROOT).json()["status"] == "pending"
    service.sync_pending(client)
    assert server.playlist == ["b", "a"]
    assert api.put(ROOT, json={"enabled": False}).json()["status"] == "disabled"
    programme(sf)
    service.sync_pending(client)
    assert server.playlist == ["b", "a"]
    api.put(ROOT, json={"enabled": True})
    service.sync_pending(client)
    assert server.playlist == ["a", "b", "a"]
    assert api.get("/radio/schedules/2026-01-01/navidrome").status_code == 404
    assert api.put("/radio/schedules/2026-01-01/navidrome", json={}).status_code == 404


@pytest.mark.parametrize("ambiguous", [False, True])
def test_unmatched_files_leave_existing_playlist_intact(
    clean_album_tables: sessionmaker[Session], ambiguous: bool
) -> None:
    sf = clean_album_tables
    programme(sf)
    service = NavidromeSyncService(sf)
    service.select(DAY, True)
    server = Server()
    client = server.client()
    service.sync_pending(client)
    server.calls.clear()
    if ambiguous:
        server.songs.append({"id": "another-edition", "path": "/music/A/two.flac"})
    else:
        server.songs.pop()
    programme(sf, reverse=True)
    service.sync_pending(client)
    status = service.status(DAY)
    assert status and status.status == "error"
    assert status.unmatched_paths == ["A/two.flac"]
    assert server.playlist == ["a", "b", "a"]
    assert all(endpoint != "createPlaylist" for endpoint, _ in server.calls)
    server.songs = [
        {"id": "a", "path": "/music/A/one.flac"},
        {"id": "b", "path": "/music/A/two.flac"},
    ]
    service.sync_pending(client)  # error rows retry automatically after the next scan
    assert service.status(DAY).status == "synced"  # type: ignore[union-attr]


def test_outage_and_lost_create_response_recover(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    programme(sf)
    service = NavidromeSyncService(sf)
    service.select(DAY, True)
    server = Server()
    client = server.client()
    server.fail = True
    service.sync_pending(client)
    status = service.status(DAY)
    assert status and status.status == "error" and "secret" not in (status.error or "")
    server.fail = False
    server.lose_create_response = True
    service.sync_pending(client)
    assert server.exists
    assert service.status(DAY).playlist_id is None  # type: ignore[union-attr]
    service.sync_pending(client)
    assert service.status(DAY).status == "synced"  # type: ignore[union-attr]
    creates = [params for endpoint, params in server.calls if endpoint == "createPlaylist"]
    assert "name" in creates[0] and creates[1]["playlistId"] == ["p1"]


def test_readback_mismatch_is_not_success(clean_album_tables: sessionmaker[Session]) -> None:
    programme(clean_album_tables)
    service = NavidromeSyncService(clean_album_tables)
    service.select(DAY, True)
    server = Server()
    server.corrupt_readback = True
    service.sync_pending(server.client())
    status = service.status(DAY)
    assert status and status.status == "error" and status.playlist_id == "p1"
    assert status.last_synced_at is None


def test_sharing_failure_recovers_existing_playlist_without_duplicates() -> None:
    server = Server()
    client = server.client()
    server.fail_sharing = True
    with pytest.raises(NavidromeError, match="updatePlaylist"):
        client.replace_playlist("MCM Radio — 2026-10-19", None, ["a", "b"])
    assert server.exists and not server.public
    server.fail_sharing = False
    playlist_id = client.replace_playlist("MCM Radio — 2026-10-19", None, ["a", "b"])
    assert playlist_id == "p1" and server.public
    client.verify_playlist(playlist_id, ["a", "b"])
    creates = [params for endpoint, params in server.calls if endpoint == "createPlaylist"]
    assert "name" in creates[0] and creates[1]["playlistId"] == ["p1"]


def test_private_readback_is_not_success() -> None:
    server = Server()
    client = server.client()
    playlist_id = client.replace_playlist("MCM Radio — 2026-10-19", None, ["a"])
    server.public = False
    with pytest.raises(NavidromeError, match="not visible"):
        client.verify_playlist(playlist_id, ["a"])


def test_updating_an_existing_private_playlist_shares_it() -> None:
    server = Server()
    server.exists = True
    client = server.client()
    assert client.replace_playlist("MCM Radio — 2026-10-19", "p1", ["b", "a"]) == "p1"
    assert server.public
    client.verify_playlist("p1", ["b", "a"])


def test_path_roots_and_scheduler_independence() -> None:
    assert relative_path("/music/A/one.flac", "/music") == "A/one.flac"
    assert relative_path("/music-other/A/one.flac", "/music") is None
    assert relative_path("A/../one.flac") is None
    assert relative_path("/A/one.flac") is None
    assert relative_path("A/One.flac") != relative_path("A/one.flac")
    scheduler = build_scheduler(Settings(navidrome_url="https://nd.example"))
    ids = {job.id for job in scheduler.get_jobs()}
    assert "navidrome" in ids and "radio_load" not in ids
    ids = {job.id for job in build_scheduler(Settings(mpd_host="mpd")).get_jobs()}
    assert "radio_load" in ids and "navidrome" not in ids


def test_username_password_authentication_and_prefix() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        params = parse_qs(request.content.decode())
        assert params["u"] == ["billy"] and "apiKey" not in params
        assert len(params["t"][0]) == 32 and params["s"]
        return httpx.Response(
            200, json={"subsonic-response": {"status": "ok", "searchResult3": {}}}
        )

    client = NavidromeClient(
        Settings(
            navidrome_url="https://nd.example",
            navidrome_username="billy",
            navidrome_password="secret",
            navidrome_path_prefix="/music",
        ),
        httpx.Client(transport=httpx.MockTransport(handle)),
    )
    assert client.song_index() == {}
    client.settings.navidrome_username = ""
    with pytest.raises(NavidromeError, match="credentials"):
        client.song_index()


def test_virtual_paths_are_rejected_before_playlist_writes() -> None:
    server = Server()
    server.songs = [{"id": "a", "path": "A/Album/01 Title.flac"}]
    with pytest.raises(NavidromeError, match="Report Real Path"):
        server.client().song_index()
    assert [endpoint for endpoint, _ in server.calls] == ["search3"]


def test_two_workers_cannot_claim_the_same_programme(
    clean_album_tables: sessionmaker[Session],
) -> None:
    from sqlalchemy import select

    from mcm.models import RadioNavidromeSync

    programme(clean_album_tables)
    service = NavidromeSyncService(clean_album_tables)
    service.select(DAY, True)
    server = Server()
    with clean_album_tables() as session:
        session.scalar(select(RadioNavidromeSync).with_for_update())
        service.sync_pending(server.client())
        assert all(endpoint == "search3" for endpoint, _ in server.calls)
    service.sync_pending(server.client())
    assert service.status(DAY).status == "synced"  # type: ignore[union-attr]
