from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.decide import DecideService
from wantlist.models import Album, AlbumState, PlayHistory, Provenance

from .fakes import FrozenClock

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _add(
    sf: sessionmaker[Session],
    *,
    title: str,
    saved_days_ago: int,
    state: AlbumState = AlbumState.saved,
    snoozed_until: datetime | None = None,
) -> str:
    """Adds an album (spotify_id == title) and returns its spotify_id."""
    with sf() as session:
        session.add(
            Album(
                spotify_id=title,
                artist="A",
                title=title,
                state=state,
                provenance=Provenance.spotify_save,
                saved_at=NOW - timedelta(days=saved_days_ago),
                snoozed_until=snoozed_until,
            )
        )
        session.commit()
    return title


def _play(sf: sessionmaker[Session], album_id: str, track: str, days_ago: int) -> None:
    with sf() as session:
        session.add(
            PlayHistory(
                spotify_track_id=track,
                spotify_album_id=album_id,
                played_at=NOW - timedelta(days=days_ago),
            )
        )
        session.commit()


def _svc(sf: sessionmaker[Session]) -> DecideService:
    return DecideService(
        repo=AlbumRepo(sf),
        clock=FrozenClock(NOW),
        forgotten_days=21,
        snooze_days=14,
        listened_tracks=4,
        listened_days=3,
    )


def _id(sf: sessionmaker[Session], title: str) -> int:
    return next(a.id for a in AlbumRepo(sf).list_albums() if a.title == title)


def test_forgotten_trigger_surfaces_old_saves(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _add(sf, title="old", saved_days_ago=30)
    _add(sf, title="recent", saved_days_ago=5)  # not old, not played
    queue = _svc(sf).queue()
    assert [i.title for i in queue] == ["old"]
    assert queue[0].reason == "saved 30d ago"


def test_listened_trigger_surfaces_recent_but_played(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="fresh-but-played", saved_days_ago=5)  # too new for the forgotten trigger
    for i in range(4):  # 4 distinct tracks >= listened_tracks
        _play(sf, "fresh-but-played", f"t{i}", days_ago=2)
    queue = _svc(sf).queue()
    assert [i.title for i in queue] == ["fresh-but-played"]
    assert queue[0].reason == "played 4 tracks"


def test_not_surfaced_when_neither_trigger_fires(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="quiet", saved_days_ago=5)
    _play(sf, "quiet", "t0", days_ago=1)  # only 1 track, 1 day
    assert _svc(sf).queue() == []


def test_snoozed_is_excluded(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _add(sf, title="x", saved_days_ago=30, snoozed_until=NOW + timedelta(days=3))
    assert _svc(sf).queue() == []


def test_keep_drop_snooze_transitions(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _add(sf, title="k", saved_days_ago=30)
    _svc(sf).keep(_id(sf, "k"))
    assert {a.title: a.state for a in AlbumRepo(sf).list_albums()} == {"k": "wanted"}

    _add(sf, title="d", saved_days_ago=30)
    _svc(sf).drop(_id(sf, "d"))
    states = {a.title: a.state for a in AlbumRepo(sf).list_albums()}
    assert states["d"] == "dismissed"

    _add(sf, title="s", saved_days_ago=30)
    _svc(sf).snooze(_id(sf, "s"))
    assert "s" not in [i.title for i in _svc(sf).queue()]
