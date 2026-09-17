from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.beets import BeetsAlbum, BeetsTrack
from mcm.adapters.beets_cache import BeetsCatalogCache
from mcm.app import create_app
from mcm.config import Settings
from mcm.radio_catalogue import RadioCatalogueService


def _client(sf: sessionmaker[Session]) -> TestClient:
    app = create_app(Settings())
    app.state.radio_catalogue_service = RadioCatalogueService(sf)
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
