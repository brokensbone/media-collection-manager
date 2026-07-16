from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from wantlist.acquire import AcquireService
from wantlist.adapters.album_repo import AlbumRepo
from wantlist.models import Album, AlbumState, Provenance
from wantlist.reconcile import OwnershipReconciler

from .fakes import FrozenClock, StubOwnedReleaseGroups

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def _add(
    sf: sessionmaker[Session], *, title: str, state: AlbumState, rgid: str | None = None
) -> None:
    with sf() as session:
        session.add(
            Album(
                spotify_id=title,
                artist="A",
                title=title,
                state=state,
                provenance=Provenance.spotify_save,
                mb_releasegroup_id=rgid,
            )
        )
        session.commit()


def _svc(sf: sessionmaker[Session]) -> AcquireService:
    return AcquireService(repo=AlbumRepo(sf), clock=FrozenClock(NOW))


def _id(sf: sessionmaker[Session], title: str) -> int:
    return next(a.id for a in AlbumRepo(sf).list_albums() if a.title == title)


def test_queue_lists_only_wanted_with_bandcamp_link(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="want-it", state=AlbumState.wanted)
    _add(sf, title="still-saved", state=AlbumState.saved)
    _add(sf, title="already-owned", state=AlbumState.owned)
    queue = _svc(sf).queue()
    assert [i.title for i in queue] == ["want-it"]
    assert queue[0].bandcamp_url.startswith("https://bandcamp.com/search?q=")


def test_mark_ordered_drops_out_then_cancel_restores(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="x", state=AlbumState.wanted)
    svc = _svc(sf)
    svc.mark_ordered(_id(sf, "x"))
    assert svc.queue() == []  # acquiring drops out of the buy list
    svc.cancel_order(_id(sf, "x"))
    assert [i.title for i in svc.queue()] == ["x"]


def test_mark_owned_survives_reconcile(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _add(sf, title="deluxe-i-own", state=AlbumState.wanted, rgid="rg-standard")
    _svc(sf).mark_owned(_id(sf, "deluxe-i-own"))
    # beets doesn't know rg-standard, but the manual link must stay owned
    OwnershipReconciler(beets=StubOwnedReleaseGroups(set()), repo=AlbumRepo(sf)).reconcile()
    assert {a.title: a.owned for a in AlbumRepo(sf).list_albums()} == {"deluxe-i-own": True}


def test_reconcile_promotes_acquiring_to_owned(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="ordered", state=AlbumState.wanted, rgid="rg-1")
    _svc(sf).mark_ordered(_id(sf, "ordered"))  # -> acquiring
    OwnershipReconciler(beets=StubOwnedReleaseGroups({"rg-1"}), repo=AlbumRepo(sf)).reconcile()
    assert {a.title: a.owned for a in AlbumRepo(sf).list_albums()} == {"ordered": True}
