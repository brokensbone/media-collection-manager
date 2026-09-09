import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from ..models import WorkerEvent

log = logging.getLogger(__name__)

_KEEP = 2000  # recent-window size; the feed is a live tail, not an audit trail
_PRUNE_EVERY = 200  # amortise the prune DELETE over inserts


@dataclass
class EventRow:
    id: int
    created_at: datetime
    job: str
    type: str
    message: str
    album_id: int | None


class WorkerEventLog:
    """DB-backed activity log. The worker `emit`s rows; the API `recent`-tails them (they can't
    share memory across processes). Kept to a recent window so it can't grow without bound."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory
        self._since_prune = 0

    def emit(self, *, job: str, type: str, message: str, album_id: int | None = None) -> None:
        # Never let logging break the actual work: a feed write failing must not abort a poll.
        try:
            with self._sf() as session:
                row = WorkerEvent(job=job, type=type, message=message, album_id=album_id)
                session.add(row)
                session.commit()
                new_id = row.id
            self._maybe_prune(new_id)
        except Exception:
            log.warning("worker event emit failed (job=%s type=%s)", job, type, exc_info=True)

    def recent(self, after: int | None = None, limit: int = 100) -> list[EventRow]:
        """Ascending by id. With `after`, only rows newer than that cursor (the poll path);
        without it, the latest `limit` rows (the first page)."""
        with self._sf() as session:
            if after is not None:
                rows = session.scalars(
                    select(WorkerEvent)
                    .where(WorkerEvent.id > after)
                    .order_by(WorkerEvent.id.asc())
                    .limit(limit)
                ).all()
            else:
                latest = session.scalars(
                    select(WorkerEvent).order_by(WorkerEvent.id.desc()).limit(limit)
                ).all()
                rows = list(reversed(latest))
            return [
                EventRow(r.id, r.created_at, r.job, r.type, r.message, r.album_id) for r in rows
            ]

    def _maybe_prune(self, new_id: int) -> None:
        if new_id - self._since_prune < _PRUNE_EVERY:
            return
        self._since_prune = new_id
        with self._sf() as session:
            session.execute(delete(WorkerEvent).where(WorkerEvent.id <= new_id - _KEEP))
            session.commit()


class NullEventSink:
    """No-op sink: the default for the API and tests, which don't emit activity."""

    def emit(self, *, job: str, type: str, message: str, album_id: int | None = None) -> None:
        pass
