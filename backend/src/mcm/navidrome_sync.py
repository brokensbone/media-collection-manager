"""Durable, independently retryable Navidrome destination for radio programmes."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .adapters.navidrome import NavidromeClient, NavidromeError, relative_path
from .models import RadioNavidromeSync, RadioSchedule
from .radio_schedules import RadioScheduleService, ScheduleError


@dataclass
class NavidromeSyncView:
    enabled: bool = False
    status: str = "disabled"
    playlist_id: str | None = None
    last_synced_at: datetime | None = None
    last_attempt_at: datetime | None = None
    error: str | None = None
    unmatched_paths: list[str] | None = None
    track_count: int = 0


def _view(row: RadioNavidromeSync | None) -> NavidromeSyncView:
    if row is None:
        return NavidromeSyncView(unmatched_paths=[])
    return NavidromeSyncView(
        row.enabled,
        row.status,
        row.playlist_id,
        row.last_synced_at,
        row.last_attempt_at,
        row.error,
        row.unmatched_paths,
        row.track_count,
    )


class NavidromeSyncService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def status(self, day: date) -> NavidromeSyncView | None:
        with self._sf() as session:
            schedule = session.scalar(
                select(RadioSchedule).where(RadioSchedule.schedule_date == day)
            )
            if schedule is None:
                return None
            return _view(session.get(RadioNavidromeSync, schedule.id))

    def select(self, day: date, enabled: bool) -> NavidromeSyncView | None:
        with self._sf() as session:
            # Serialize first-time selection too, where no destination row exists yet.
            schedule = session.scalar(
                select(RadioSchedule).where(RadioSchedule.schedule_date == day).with_for_update()
            )
            if schedule is None:
                return None
            row = session.scalar(
                select(RadioNavidromeSync)
                .where(RadioNavidromeSync.schedule_id == schedule.id)
                .with_for_update()
            )
            if row is None:
                row = RadioNavidromeSync(schedule_id=schedule.id)
                session.add(row)
            row.enabled = enabled
            row.status = "pending" if enabled else "disabled"
            row.error = None
            row.unmatched_paths = []
            session.commit()
            return _view(row)

    def sync_pending(self, client: NavidromeClient) -> None:
        with self._sf() as session:
            ids = list(
                session.scalars(
                    select(RadioNavidromeSync.schedule_id).where(
                        RadioNavidromeSync.enabled.is_(True),
                        RadioNavidromeSync.status.in_(["pending", "error"]),
                    )
                )
            )
        if not ids:
            return
        # Fetch before acquiring destination locks so a large library scan does not
        # block programme edits or destination changes. Share this snapshot across dates.
        index: dict[str, set[str]] | None = None
        index_error: NavidromeError | None = None
        try:
            index = client.song_index()
        except NavidromeError as exc:
            index_error = exc
        for schedule_id in ids:
            with self._sf() as session:
                row = session.scalar(
                    select(RadioNavidromeSync)
                    .where(
                        RadioNavidromeSync.schedule_id == schedule_id,
                        RadioNavidromeSync.enabled.is_(True),
                        RadioNavidromeSync.status.in_(["pending", "error"]),
                    )
                    .with_for_update(skip_locked=True)
                )
                if row is None:
                    continue
                schedule = session.get(RadioSchedule, schedule_id)
                assert schedule is not None
                row.last_attempt_at = datetime.now(UTC)
                row.unmatched_paths = []
                try:
                    paths = RadioScheduleService(self._sf).playable_paths(schedule.schedule_date)
                    if not paths:
                        raise ScheduleError("schedule has no playable tracks")
                    if index_error is not None:
                        raise index_error
                    assert index is not None
                    unmatched = [
                        p for p in paths if len(index.get(relative_path(p) or "", set())) != 1
                    ]
                    if unmatched:
                        row.unmatched_paths = list(dict.fromkeys(unmatched))
                        raise NavidromeError("Missing or ambiguous files; playlist was not changed")
                    songs = [next(iter(index[relative_path(p) or ""])) for p in paths]
                    row.playlist_id = client.replace_playlist(
                        f"MCM Radio — {schedule.schedule_date.isoformat()}", row.playlist_id, songs
                    )
                    client.verify_playlist(row.playlist_id, songs)
                    row.track_count = len(songs)
                    row.status = "synced"
                    row.error = None
                    row.last_synced_at = datetime.now(UTC)
                except (NavidromeError, ScheduleError) as exc:
                    row.status = "error"
                    row.error = str(exc)
                session.commit()
