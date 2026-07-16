from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session, sessionmaker

from ..models import Album, AlbumArt, AlbumState, LinkSource, Provenance


@dataclass
class UnresolvedAlbum:
    id: int
    spotify_id: str | None
    upc: str | None
    artist: str
    title: str


@dataclass
class AlbumSummary:
    id: int
    artist: str
    title: str
    state: str
    mb_releasegroup_id: str | None
    owned: bool
    has_art: bool


class AlbumRepo:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def existing_spotify_ids(self) -> set[str]:
        with self._sf() as session:
            rows = session.scalars(select(Album.spotify_id).where(Album.spotify_id.is_not(None)))
            return {r for r in rows if r is not None}

    def add_saved_album(
        self,
        *,
        spotify_id: str,
        artist: str,
        title: str,
        upc: str | None,
        added_at: datetime | None,
        art_url: str | None,
    ) -> None:
        with self._sf() as session:
            session.add(
                Album(
                    spotify_id=spotify_id,
                    artist=artist,
                    title=title,
                    upc=upc,
                    art_url=art_url,
                    saved_at=added_at,
                    state=AlbumState.saved,
                    provenance=Provenance.spotify_save,
                )
            )
            session.commit()

    def albums_missing_art(self) -> list[tuple[int, str]]:
        """Albums that have a source URL but no stored blob yet."""
        with self._sf() as session:
            rows = session.execute(
                select(Album.id, Album.art_url)
                .outerjoin(AlbumArt, AlbumArt.album_id == Album.id)
                .where(Album.art_url.is_not(None), AlbumArt.album_id.is_(None))
            )
            return [(album_id, url) for album_id, url in rows if url is not None]

    def save_art(self, album_id: int, content_type: str, data: bytes) -> None:
        with self._sf() as session:
            session.merge(
                AlbumArt(album_id=album_id, content_type=content_type, image=data, size=len(data))
            )
            session.commit()

    def get_art(self, album_id: int) -> tuple[str, bytes] | None:
        with self._sf() as session:
            row = session.get(AlbumArt, album_id)
            return (row.content_type, row.image) if row else None

    # --- resolution (§5) -------------------------------------------------------------

    def albums_needing_resolution(self) -> list[UnresolvedAlbum]:
        """Non-dismissed albums without a release-group id yet (resolve-once, re-try tail)."""
        with self._sf() as session:
            rows = session.execute(
                select(Album.id, Album.spotify_id, Album.upc, Album.artist, Album.title).where(
                    Album.mb_releasegroup_id.is_(None),
                    Album.state != AlbumState.dismissed,
                )
            )
            return [UnresolvedAlbum(*row) for row in rows]

    def set_release_group(self, album_id: int, mb_releasegroup_id: str) -> None:
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id)
                .values(mb_releasegroup_id=mb_releasegroup_id)
            )
            session.commit()

    # --- ownership reconcile (§5) ----------------------------------------------------

    def resolvable_unowned(self) -> list[tuple[int, str]]:
        """(id, release-group id) for albums that could still auto-resolve to owned:
        have a release-group id, not already owned, and not a manual link (never clobbered)."""
        with self._sf() as session:
            rows = session.execute(
                select(Album.id, Album.mb_releasegroup_id).where(
                    Album.mb_releasegroup_id.is_not(None),
                    Album.state != AlbumState.owned,
                    Album.owned_link_source.is_distinct_from(LinkSource.manual),
                )
            )
            return [(album_id, rgid) for album_id, rgid in rows]

    def mark_owned_auto(self, album_ids: list[int]) -> None:
        if not album_ids:
            return
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id.in_(album_ids))
                .values(state=AlbumState.owned, owned_link_source=LinkSource.auto)
            )
            session.commit()

    # --- library view ----------------------------------------------------------------

    def list_albums(self, state: str | None = None) -> list[AlbumSummary]:
        with self._sf() as session:
            has_art = exists().where(AlbumArt.album_id == Album.id)
            stmt = select(
                Album.id,
                Album.artist,
                Album.title,
                Album.state,
                Album.mb_releasegroup_id,
                has_art,
            ).order_by(Album.artist, Album.title)
            if state is not None:
                stmt = stmt.where(Album.state == AlbumState(state))
            return [
                AlbumSummary(
                    id=row[0],
                    artist=row[1],
                    title=row[2],
                    state=row[3].value,
                    mb_releasegroup_id=row[4],
                    owned=row[3] == AlbumState.owned,
                    has_art=row[5],
                )
                for row in session.execute(stmt)
            ]
