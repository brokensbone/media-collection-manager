from datetime import UTC, datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session, sessionmaker

from ..models import BeetsAlbumCache, BeetsTrackCache
from .beets import BeetsAlbum, BeetsTrack


class BeetsCatalogCache:
    """The DB-cached beets catalogue (models.BeetsAlbumCache). `all_albums` is the read side the
    API uses — same shape as BeetsClient, so it satisfies the LibraryCatalog seam and drops in
    wherever the catalogue is read, with no live `beet` call. `replace` is the worker's atomic
    refresh (delete + insert in one transaction, so readers never see a half-empty catalogue)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def all_albums(self) -> list[BeetsAlbum]:
        with self._sf() as session:
            rows = session.execute(
                select(
                    BeetsAlbumCache.beets_id,
                    BeetsAlbumCache.artist,
                    BeetsAlbumCache.title,
                    BeetsAlbumCache.mb_releasegroup_id,
                    BeetsAlbumCache.year,
                    BeetsAlbumCache.media,
                    BeetsAlbumCache.label,
                    BeetsAlbumCache.country,
                    BeetsAlbumCache.secondary_types,
                    BeetsAlbumCache.genre,
                    BeetsAlbumCache.added_at,
                )
            )
            return [
                BeetsAlbum(
                    beets_id=r[0],
                    artist=r[1],
                    title=r[2],
                    mb_releasegroup_id=r[3],
                    year=r[4],
                    media=r[5],
                    label=r[6],
                    country=r[7],
                    secondary_types=r[8],
                    genre=r[9],
                    added_at=r[10],
                )
                for r in rows
            ]

    def replace(self, albums: list[BeetsAlbum], tracks: list[BeetsTrack] | None = None) -> None:
        """Atomically replace the whole worker-owned snapshot.

        `tracks=None` preserves the old caller contract for focused tests and for consumers that
        only refresh album metadata. A normal worker pass supplies both lists.
        """
        refreshed_at = datetime.now(UTC)
        with self._sf() as session:
            session.execute(delete(BeetsTrackCache))
            session.execute(delete(BeetsAlbumCache))
            if albums:
                session.execute(
                    insert(BeetsAlbumCache),
                    [
                        {
                            "beets_id": a.beets_id,
                            "artist": a.artist,
                            "title": a.title,
                            "mb_releasegroup_id": a.mb_releasegroup_id,
                            "year": a.year,
                            "media": a.media,
                            "label": a.label,
                            "country": a.country,
                            "secondary_types": a.secondary_types,
                            "genre": a.genre,
                            "added_at": a.added_at,
                            "refreshed_at": refreshed_at,
                        }
                        for a in albums
                    ],
                )
            if tracks:
                session.execute(
                    insert(BeetsTrackCache),
                    [
                        {
                            "item_id": t.item_id,
                            "beets_id": t.beets_id,
                            "disc": t.disc,
                            "track": t.track,
                            "title": t.title,
                            "duration_seconds": t.duration_seconds,
                            "path": t.path,
                        }
                        for t in tracks
                    ],
                )
            session.commit()
