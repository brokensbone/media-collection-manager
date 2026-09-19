from datetime import datetime
from zoneinfo import ZoneInfo

from _pytest.monkeypatch import MonkeyPatch
from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.beets import BeetsAlbum, BeetsTrack
from mcm.adapters.beets_cache import BeetsCatalogCache
from mcm.config import Settings
from mcm.jobs import load_radio_once, play_radio_once
from mcm.radio_schedules import (
    RadioScheduleService,
    ScheduleInput,
    ScheduleItemInput,
    ScheduleSessionInput,
)


def _today_schedule(session_factory: sessionmaker[Session]) -> list[str]:
    cache = BeetsCatalogCache(session_factory)
    cache.replace(
        [BeetsAlbum("1", "Artist", "Album", None)],
        [BeetsTrack("1", "11", 1, 1, "One", 100, "artist/album/one.flac")],
    )
    paths = ["artist/album/one.flac"]
    RadioScheduleService(session_factory).replace(
        datetime.now(ZoneInfo("Europe/London")).date(),
        ScheduleInput(
            note=None,
            sessions=[
                ScheduleSessionInput(
                    kind="track_hour",
                    title="Morning",
                    starts_at="09:00",
                    note=None,
                    items=[ScheduleItemInput(kind="track", beets_id=None, item_id="11")],
                )
            ],
        ),
    )
    return paths


def test_radio_load_then_play_only_when_the_queue_still_matches(
    clean_album_tables: sessionmaker[Session], monkeypatch: MonkeyPatch
) -> None:
    expected = _today_schedule(clean_album_tables)
    calls: list[object] = []

    class FakeMpd:
        queue: list[str] = []

        def __init__(self, host: str, port: int) -> None:
            calls.append((host, port))

        def load(self, paths: list[str]) -> None:
            FakeMpd.queue = paths
            calls.append(("load", paths))

        def playlist_paths(self) -> list[str]:
            calls.append("playlistinfo")
            return FakeMpd.queue

        def play(self) -> None:
            calls.append("play")

    monkeypatch.setattr("mcm.jobs._session_factory", lambda _: clean_album_tables)
    monkeypatch.setattr("mcm.jobs.MpdClient", FakeMpd)
    settings = Settings(mpd_host="mpd.example")
    load_radio_once(settings)
    play_radio_once(settings)
    assert ("load", expected) in calls
    assert calls[-1] == "play"

    FakeMpd.queue = ["something-else.flac"]
    play_radio_once(settings)
    assert calls[-1] == "playlistinfo"
