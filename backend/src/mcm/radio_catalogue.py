"""Read-only radio selection data, backed solely by MCM's worker-refreshed Beets cache."""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .models import BeetsAlbumCache, BeetsTrackCache


@dataclass
class RadioAlbum:
    beets_id: str
    artist: str
    title: str
    year: int | None
    genre: str | None
    media: str | None
    label: str | None
    country: str | None
    secondary_types: str | None
    added_at: datetime | None


@dataclass
class RadioTrack:
    item_id: str
    disc: int | None
    track: int | None
    title: str
    duration_seconds: float | None
    path: str


class RadioCatalogueService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def albums(self, *, genre: str | None, seed: str, limit: int) -> list[RadioAlbum]:
        with self._sf() as session:
            stmt = select(BeetsAlbumCache)
            if genre:
                stmt = stmt.where(BeetsAlbumCache.genre.ilike(f"%{genre}%"))
            albums = list(session.scalars(stmt))
        # A stable, supplied seed makes a random-looking choice reproducible in an overnight log.
        albums.sort(key=lambda a: hashlib.sha256(f"{seed}:{a.beets_id}".encode()).digest())
        return [self._album(a) for a in albums[:limit]]

    def recent_albums(self, *, limit: int) -> list[RadioAlbum]:
        with self._sf() as session:
            albums = session.scalars(
                select(BeetsAlbumCache)
                .where(BeetsAlbumCache.added_at.is_not(None))
                .order_by(BeetsAlbumCache.added_at.desc(), BeetsAlbumCache.beets_id)
                .limit(limit)
            ).all()
        return [self._album(a) for a in albums]

    def tracks(self, beets_id: str) -> list[RadioTrack]:
        with self._sf() as session:
            rows = session.scalars(
                select(BeetsTrackCache)
                .where(BeetsTrackCache.beets_id == beets_id)
                .order_by(
                    BeetsTrackCache.disc.nulls_last(),
                    BeetsTrackCache.track.nulls_last(),
                    BeetsTrackCache.item_id,
                )
            ).all()
        return [
            RadioTrack(r.item_id, r.disc, r.track, r.title, r.duration_seconds, r.path)
            for r in rows
        ]

    def refreshed_at(self) -> datetime | None:
        with self._sf() as session:
            return session.scalar(select(func.max(BeetsAlbumCache.refreshed_at)))

    @staticmethod
    def _album(album: BeetsAlbumCache) -> RadioAlbum:
        return RadioAlbum(
            album.beets_id,
            album.artist,
            album.title,
            album.year,
            album.genre,
            album.media,
            album.label,
            album.country,
            album.secondary_types,
            album.added_at,
        )
