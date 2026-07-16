from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.decide import DecideService
from wantlist.models import Album, AlbumState, Provenance

from .fakes import FrozenClock

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _add(
    sf: sessionmaker[Session],
    *,
    title: str,
    saved_days_ago: int,
    state: AlbumState = AlbumState.saved,
    snoozed_until: datetime | None = None,
) -> None:
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


def _svc(sf: sessionmaker[Session]) -> DecideService:
    return DecideService(
        repo=AlbumRepo(sf), clock=FrozenClock(NOW), forgotten_days=21, snooze_days=14
    )


def _first_id(sf: sessionmaker[Session]) -> int:
    return AlbumRepo(sf).decide_queue(NOW - timedelta(days=21), NOW)[0].id


def test_queue_surfaces_only_old_unsnoozed_saved(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="old", saved_days_ago=30)  # ready to judge
    _add(sf, title="recent", saved_days_ago=5)  # too new
    _add(sf, title="already-wanted", saved_days_ago=30, state=AlbumState.wanted)  # judged
    _add(sf, title="snoozed", saved_days_ago=30, snoozed_until=NOW + timedelta(days=3))
    queue = _svc(sf).queue()
    assert [i.title for i in queue] == ["old"]
    assert queue[0].reason == "saved 30d ago"


def test_keep_moves_to_wanted_and_leaves_queue(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="x", saved_days_ago=30)
    _svc(sf).keep(_first_id(sf))
    assert {a.title: a.state for a in AlbumRepo(sf).list_albums()} == {"x": "wanted"}
    assert _svc(sf).queue() == []


def test_drop_moves_to_dismissed(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _add(sf, title="x", saved_days_ago=30)
    _svc(sf).drop(_first_id(sf))
    assert {a.title: a.state for a in AlbumRepo(sf).list_albums()} == {"x": "dismissed"}


def test_snooze_removes_from_queue_without_a_verdict(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="x", saved_days_ago=30)
    _svc(sf).snooze(_first_id(sf))
    assert _svc(sf).queue() == []  # snoozed forward
    assert {a.title: a.state for a in AlbumRepo(sf).list_albums()} == {"x": "saved"}
