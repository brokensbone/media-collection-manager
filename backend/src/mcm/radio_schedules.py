"""Radio schedules expressed only in stable MCM catalogue identifiers."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    BeetsAlbumCache,
    BeetsTrackCache,
    RadioSchedule,
    RadioScheduleItem,
    RadioScheduleSession,
)


class ScheduleError(Exception):
    pass


@dataclass
class ScheduleItemInput:
    kind: str
    beets_id: str | None
    item_id: str | None


@dataclass
class ScheduleSessionInput:
    kind: str
    title: str
    starts_at: str | None
    note: str | None
    items: list[ScheduleItemInput]


@dataclass
class ScheduleInput:
    note: str | None
    sessions: list[ScheduleSessionInput]


@dataclass
class ScheduleItemView:
    position: int
    kind: str
    beets_id: str | None
    item_id: str | None
    artist: str | None
    title: str
    duration_seconds: float | None
    tracks: list["ScheduleItemView"] | None = None


@dataclass
class ScheduleSessionView:
    position: int
    kind: str
    title: str
    starts_at: str | None
    note: str | None
    duration_seconds: float
    items: list[ScheduleItemView]


@dataclass
class ScheduleView:
    schedule_date: date
    note: str | None
    duration_seconds: float
    sessions: list[ScheduleSessionView]


@dataclass
class ScheduleSummary:
    schedule_date: date
    note: str | None
    session_count: int
    duration_seconds: float


class RadioScheduleService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def list_schedules(self) -> list[ScheduleSummary]:
        with self._sf() as session:
            schedules = session.scalars(
                select(RadioSchedule).order_by(RadioSchedule.schedule_date.desc())
            ).all()
            return [self._summary(session, schedule) for schedule in schedules]

    def get(self, schedule_date: date) -> ScheduleView | None:
        with self._sf() as session:
            schedule = session.scalar(
                select(RadioSchedule).where(RadioSchedule.schedule_date == schedule_date)
            )
            return self._view(session, schedule) if schedule else None

    def playable_paths(self, schedule_date: date) -> list[str] | None:
        """Resolve a dated plan immediately before loading it into MPD.

        Paths remain an internal worker concern: the schedule API and its stored selections
        continue to use only catalogue identifiers.
        """
        with self._sf() as session:
            schedule = session.scalar(
                select(RadioSchedule).where(RadioSchedule.schedule_date == schedule_date)
            )
            if schedule is None:
                return None
            sessions = session.scalars(
                select(RadioScheduleSession)
                .where(RadioScheduleSession.schedule_id == schedule.id)
                .order_by(RadioScheduleSession.position)
            ).all()
            paths: list[str] = []
            for segment in sessions:
                selections = session.scalars(
                    select(RadioScheduleItem)
                    .where(RadioScheduleItem.session_id == segment.id)
                    .order_by(RadioScheduleItem.position)
                ).all()
                if not selections:
                    raise ScheduleError(f"session {segment.position + 1} has no selections")
                for selection in selections:
                    if selection.kind == "track":
                        track = session.get(BeetsTrackCache, selection.item_id)
                        if track is None or not track.path:
                            raise ScheduleError(f"unavailable playable track {selection.item_id}")
                        paths.append(track.path)
                    elif selection.kind == "album":
                        tracks = session.scalars(
                            select(BeetsTrackCache)
                            .where(BeetsTrackCache.beets_id == selection.beets_id)
                            .order_by(
                                BeetsTrackCache.disc.nulls_last(),
                                BeetsTrackCache.track.nulls_last(),
                            )
                        ).all()
                        if not tracks:
                            raise ScheduleError(f"unavailable playable album {selection.beets_id}")
                        paths.extend(track.path for track in tracks if track.path)
                    else:
                        raise ScheduleError(f"unknown schedule selection kind {selection.kind}")
            if not paths:
                raise ScheduleError("schedule has no playable tracks")
            return paths

    def replace(self, schedule_date: date, input: ScheduleInput) -> ScheduleView:
        self._validate(input)
        with self._sf() as session:
            schedule = session.scalar(
                select(RadioSchedule).where(RadioSchedule.schedule_date == schedule_date)
            )
            if schedule is None:
                schedule = RadioSchedule(schedule_date=schedule_date, note=input.note)
                session.add(schedule)
                session.flush()
            else:
                session.execute(
                    delete(RadioScheduleSession).where(
                        RadioScheduleSession.schedule_id == schedule.id
                    )
                )
                schedule.note = input.note

            for session_position, session_input in enumerate(input.sessions):
                row = RadioScheduleSession(
                    schedule_id=schedule.id,
                    position=session_position,
                    kind=session_input.kind,
                    title=session_input.title.strip(),
                    starts_at=session_input.starts_at,
                    note=session_input.note,
                )
                session.add(row)
                session.flush()
                for item_position, item in enumerate(session_input.items):
                    session.add(
                        RadioScheduleItem(
                            session_id=row.id,
                            position=item_position,
                            kind=item.kind,
                            beets_id=item.beets_id,
                            item_id=item.item_id,
                        )
                    )
            session.commit()
            return self._view(session, schedule)

    def _validate(self, input: ScheduleInput) -> None:
        if not input.sessions:
            raise ScheduleError("a schedule needs at least one session")
        with self._sf() as session:
            for segment in input.sessions:
                if segment.kind not in {"track_hour", "album_session"}:
                    raise ScheduleError("session kind must be track_hour or album_session")
                if not segment.title.strip() or not segment.items:
                    raise ScheduleError("every session needs a title and at least one selection")
                expected_item_kind = "track" if segment.kind == "track_hour" else "album"
                for item in segment.items:
                    if item.kind != expected_item_kind:
                        raise ScheduleError(
                            f"{segment.kind} sessions can only contain "
                            f"{expected_item_kind} selections"
                        )
                    if item.kind == "track":
                        if not item.item_id or session.get(BeetsTrackCache, item.item_id) is None:
                            raise ScheduleError(f"unknown playable track {item.item_id}")
                    elif not item.beets_id or session.get(BeetsAlbumCache, item.beets_id) is None:
                        raise ScheduleError(f"unknown playable album {item.beets_id}")

    def _summary(self, session: Session, schedule: RadioSchedule) -> ScheduleSummary:
        view = self._view(session, schedule)
        return ScheduleSummary(
            schedule_date=view.schedule_date,
            note=view.note,
            session_count=len(view.sessions),
            duration_seconds=view.duration_seconds,
        )

    def _view(self, session: Session, schedule: RadioSchedule) -> ScheduleView:
        sessions = session.scalars(
            select(RadioScheduleSession)
            .where(RadioScheduleSession.schedule_id == schedule.id)
            .order_by(RadioScheduleSession.position)
        ).all()
        segments = [self._session_view(session, row) for row in sessions]
        return ScheduleView(
            schedule_date=schedule.schedule_date,
            note=schedule.note,
            duration_seconds=sum(s.duration_seconds for s in segments),
            sessions=segments,
        )

    def _session_view(self, session: Session, row: RadioScheduleSession) -> ScheduleSessionView:
        rows = session.scalars(
            select(RadioScheduleItem)
            .where(RadioScheduleItem.session_id == row.id)
            .order_by(RadioScheduleItem.position)
        ).all()
        items = [self._item_view(session, item) for item in rows]
        return ScheduleSessionView(
            position=row.position,
            kind=row.kind,
            title=row.title,
            starts_at=row.starts_at,
            note=row.note,
            duration_seconds=sum(item.duration_seconds or 0 for item in items),
            items=items,
        )

    def _item_view(self, session: Session, item: RadioScheduleItem) -> ScheduleItemView:
        if item.kind == "track":
            track = session.get(BeetsTrackCache, item.item_id)
            if track is None:
                return ScheduleItemView(
                    item.position, "track", None, item.item_id, None, "Unavailable track", None
                )
            album = session.get(BeetsAlbumCache, track.beets_id)
            return ScheduleItemView(
                item.position,
                "track",
                track.beets_id,
                track.item_id,
                album.artist if album else None,
                track.title,
                track.duration_seconds,
            )
        album = session.get(BeetsAlbumCache, item.beets_id)
        if album is None:
            return ScheduleItemView(
                item.position, "album", item.beets_id, None, None, "Unavailable album", None, []
            )
        tracks = session.scalars(
            select(BeetsTrackCache)
            .where(BeetsTrackCache.beets_id == album.beets_id)
            .order_by(BeetsTrackCache.disc.nulls_last(), BeetsTrackCache.track.nulls_last())
        ).all()
        track_views = [
            ScheduleItemView(
                position,
                "track",
                album.beets_id,
                track.item_id,
                album.artist,
                track.title,
                track.duration_seconds,
            )
            for position, track in enumerate(tracks)
        ]
        return ScheduleItemView(
            item.position,
            "album",
            album.beets_id,
            None,
            album.artist,
            album.title,
            sum(track.duration_seconds or 0 for track in tracks),
            track_views,
        )
