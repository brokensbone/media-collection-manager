from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.models import Album, AlbumState, LinkSource, Provenance
from wantlist.reconcile import OwnershipReconciler

from .fakes import StubOwnedReleaseGroups


def _add(
    sf: sessionmaker[Session],
    *,
    title: str,
    rgid: str,
    state: AlbumState = AlbumState.wanted,
    link: LinkSource | None = None,
) -> None:
    with sf() as session:
        session.add(
            Album(
                spotify_id=title,
                artist="A",
                title=title,
                mb_releasegroup_id=rgid,
                state=state,
                provenance=Provenance.spotify_save,
                owned_link_source=link,
            )
        )
        session.commit()


def _by_title(sf: sessionmaker[Session]) -> dict[str, bool]:
    return {a.title: a.owned for a in AlbumRepo(sf).list_albums()}


def test_reconcile_marks_matching_owned_and_leaves_rest(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    _add(sf, title="own-me", rgid="rg1")
    _add(sf, title="not-owned", rgid="rg2")
    result = OwnershipReconciler(
        beets=StubOwnedReleaseGroups({"rg1"}), repo=AlbumRepo(sf)
    ).reconcile()
    assert result.newly_owned == 1
    owned = _by_title(sf)
    assert owned == {"own-me": True, "not-owned": False}


def test_reconcile_never_touches_a_manual_link(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    # a manually-linked owned album whose rgid is NOT in beets — must stay owned
    _add(sf, title="manual", rgid="rgX", state=AlbumState.owned, link=LinkSource.manual)
    result = OwnershipReconciler(
        beets=StubOwnedReleaseGroups(set()), repo=AlbumRepo(sf)
    ).reconcile()
    assert result.newly_owned == 0
    assert _by_title(sf)["manual"] is True
