from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.beets import BeetsAlbum, BeetsTrack
from mcm.adapters.beets_cache import BeetsCatalogCache
from mcm.app import create_app
from mcm.config import Settings
from mcm.radio_catalogue import RadioCatalogueService
from mcm.radio_schedules import (
    RadioScheduleService,
    ScheduleInput,
    ScheduleItemInput,
    ScheduleSessionInput,
)


def _client(sf: sessionmaker[Session]) -> TestClient:
    app = create_app(Settings())
    app.state.radio_catalogue_service = RadioCatalogueService(sf)
    app.state.radio_schedule_service = RadioScheduleService(sf)
    return TestClient(app)


def test_radio_catalogue_filters_deterministically_and_returns_mpd_paths(
    clean_album_tables: sessionmaker[Session],
) -> None:
    cache = BeetsCatalogCache(clean_album_tables)
    cache.replace(
        [
            BeetsAlbum("1", "Burial", "Untrue", None, genre="Dubstep"),
            BeetsAlbum("2", "Four Tet", "Rounds", None, genre="Electronic"),
            BeetsAlbum("3", "Kode9", "Nothing", None, genre="Dubstep"),
        ],
        [BeetsTrack("1", "11", 1, 1, "Archangel", 230.5, "Burial/Untrue/01 Archangel.flac")],
    )
    client = _client(clean_album_tables)

    first = client.get("/radio/albums", params={"genre": "dubstep", "seed": "monday"})
    second = client.get("/radio/albums", params={"genre": "dubstep", "seed": "monday"})
    assert first.status_code == 200 and first.json() == second.json()
    assert {a["beets_id"] for a in first.json()} == {"1", "3"}

    tracks = client.get("/radio/albums/1/tracks")
    assert tracks.status_code == 200
    assert tracks.json() == [
        {
            "item_id": "11",
            "disc": 1,
            "track": 1,
            "title": "Archangel",
            "duration_seconds": 230.5,
            "path": "Burial/Untrue/01 Archangel.flac",
        }
    ]
    assert client.get("/radio/albums/2/tracks").status_code == 404


def test_radio_catalogue_exposes_recent_albums_and_cache_freshness(
    clean_album_tables: sessionmaker[Session],
) -> None:
    cache = BeetsCatalogCache(clean_album_tables)
    cache.replace(
        [
            BeetsAlbum("1", "Old", "One", None, added_at=datetime(2026, 1, 1, tzinfo=UTC)),
            BeetsAlbum("2", "New", "Two", None, added_at=datetime(2026, 2, 1, tzinfo=UTC)),
            BeetsAlbum("3", "Unknown", "Three", None),
        ]
    )
    client = _client(clean_album_tables)
    recent = client.get("/radio/albums/recent").json()
    assert [a["beets_id"] for a in recent] == ["2", "1"]
    assert client.get("/radio/status").json()["catalogue_refreshed_at"] is not None


def test_radio_schedule_is_path_free_and_expands_album_contents(
    clean_album_tables: sessionmaker[Session],
) -> None:
    cache = BeetsCatalogCache(clean_album_tables)
    cache.replace(
        [BeetsAlbum("1", "Pye Corner Audio", "Hollow Earth", None)],
        [
            BeetsTrack("1", "11", 1, 1, "Mainframe", 240, "private/path.flac"),
            BeetsTrack("1", "12", 1, 2, "Electronic Rhythm Number", 300, "another/path.flac"),
        ],
    )
    client = _client(clean_album_tables)
    response = client.put(
        "/radio/schedules/2026-09-21",
        json={
            "note": "A deliberately gentle Monday.",
            "sessions": [
                {
                    "kind": "track_hour",
                    "title": "Morning club warm-up",
                    "starts_at": "09:00",
                    "items": [{"kind": "track", "item_id": "11"}],
                },
                {
                    "kind": "album_session",
                    "title": "Electronic",
                    "starts_at": "10:00",
                    "items": [{"kind": "album", "beets_id": "1"}],
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["duration_seconds"] == 780
    assert body["sessions"][1]["items"][0] == {
        "position": 0,
        "kind": "album",
        "beets_id": "1",
        "item_id": None,
        "artist": "Pye Corner Audio",
        "title": "Hollow Earth",
        "duration_seconds": 540,
        "tracks": [
            {
                "position": 0,
                "kind": "track",
                "beets_id": "1",
                "item_id": "11",
                "artist": "Pye Corner Audio",
                "title": "Mainframe",
                "duration_seconds": 240,
                "tracks": None,
            },
            {
                "position": 1,
                "kind": "track",
                "beets_id": "1",
                "item_id": "12",
                "artist": "Pye Corner Audio",
                "title": "Electronic Rhythm Number",
                "duration_seconds": 300,
                "tracks": None,
            },
        ],
    }
    assert "path" not in str(body)
    summary = client.get("/radio/schedules").json()[0]
    assert summary["schedule_date"] == "2026-09-21"
    assert "state" not in summary
    assert "state" not in body


def test_radio_schedule_rejects_an_unavailable_selection(
    clean_album_tables: sessionmaker[Session],
) -> None:
    client = _client(clean_album_tables)
    response = client.put(
        "/radio/schedules/2026-09-21",
        json={
            "sessions": [
                {
                    "kind": "track_hour",
                    "title": "No cache",
                    "items": [{"kind": "track", "item_id": "missing"}],
                }
            ]
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "unknown playable track missing"


def test_radio_schedule_resolves_paths_only_for_the_worker(
    clean_album_tables: sessionmaker[Session],
) -> None:
    cache = BeetsCatalogCache(clean_album_tables)
    cache.replace(
        [BeetsAlbum("1", "Artist", "Album", None)],
        [
            BeetsTrack("1", "11", 1, 1, "One", 100, "artist/album/one.flac"),
            BeetsTrack("1", "12", 1, 2, "Two", 100, "artist/album/two.flac"),
        ],
    )
    service = RadioScheduleService(clean_album_tables)
    day = datetime.now(ZoneInfo("Europe/London")).date()
    service.replace(
        day,
        ScheduleInput(
            note=None,
            sessions=[
                ScheduleSessionInput(
                    kind="track_hour",
                    title="Tracks",
                    starts_at="09:00",
                    note=None,
                    items=[ScheduleItemInput(kind="track", beets_id=None, item_id="12")],
                ),
                ScheduleSessionInput(
                    kind="album_session",
                    title="Album",
                    starts_at="10:00",
                    note=None,
                    items=[ScheduleItemInput(kind="album", beets_id="1", item_id=None)],
                ),
            ],
        ),
    )
    assert service.playable_paths(day) == [
        "artist/album/two.flac",
        "artist/album/one.flac",
        "artist/album/two.flac",
    ]
