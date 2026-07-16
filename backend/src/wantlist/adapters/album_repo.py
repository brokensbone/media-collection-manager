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


@dataclass
class DecideRow:
    id: int
    artist: str
    title: str
    saved_at: datetime
    has_art: bool


@dataclass
class AcquireRow:
    id: int
    artist: str
    title: str
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

    # --- verdict / Decide (§6a) ------------------------------------------------------

    def decide_queue(self, cutoff: datetime, now: datetime) -> list[DecideRow]:
        """Saved albums ready to judge: awaiting a verdict, saved before the cutoff (the
        'forgotten' trigger), and not currently snoozed. Oldest first."""
        with self._sf() as session:
            has_art = exists().where(AlbumArt.album_id == Album.id)
            rows = session.execute(
                select(Album.id, Album.artist, Album.title, Album.saved_at, has_art)
                .where(
                    Album.state == AlbumState.saved,
                    Album.saved_at.is_not(None),
                    Album.saved_at <= cutoff,
                    (Album.snoozed_until.is_(None)) | (Album.snoozed_until <= now),
                )
                .order_by(Album.saved_at)
            )
            return [DecideRow(r[0], r[1], r[2], r[3], r[4]) for r in rows]

    def set_verdict(self, album_id: int, state: AlbumState, verdict_at: datetime) -> None:
        """Keep/drop: only a `saved` album can receive a verdict."""
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id, Album.state == AlbumState.saved)
                .values(state=state, verdict_at=verdict_at)
            )
            session.commit()

    def snooze(self, album_id: int, snoozed_until: datetime) -> None:
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id, Album.state == AlbumState.saved)
                .values(snoozed_until=snoozed_until)
            )
            session.commit()

    # --- acquire (§7) ----------------------------------------------------------------

    def acquire_queue(self) -> list[AcquireRow]:
        """`wanted` albums to buy — `acquiring` (ordered) ones have dropped out."""
        with self._sf() as session:
            has_art = exists().where(AlbumArt.album_id == Album.id)
            rows = session.execute(
                select(Album.id, Album.artist, Album.title, has_art)
                .where(Album.state == AlbumState.wanted)
                .order_by(Album.artist, Album.title)
            )
            return [AcquireRow(r[0], r[1], r[2], r[3]) for r in rows]

    def mark_ordered(self, album_id: int, ordered_at: datetime) -> None:
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id, Album.state == AlbumState.wanted)
                .values(state=AlbumState.acquiring, ordered_at=ordered_at)
            )
            session.commit()

    def cancel_order(self, album_id: int) -> None:
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id, Album.state == AlbumState.acquiring)
                .values(state=AlbumState.wanted, ordered_at=None)
            )
            session.commit()

    def mark_owned_manual(self, album_id: int, beets_id: str | None) -> None:
        """A sticky manual ownership link (§4/§5) — reconcile never clobbers it. Closes the
        loop for edition mismatches and MB-absent albums."""
        with self._sf() as session:
            session.execute(
                update(Album)
                .where(Album.id == album_id)
                .values(
                    state=AlbumState.owned,
                    owned_link_source=LinkSource.manual,
                    owned_beets_id=beets_id,
                )
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
