from datetime import date

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..radio_schedules import (
    RadioScheduleService,
    ScheduleError,
    ScheduleInput,
    ScheduleItemInput,
    ScheduleSessionInput,
    ScheduleSummary,
    ScheduleView,
)

router = APIRouter(prefix="/radio/schedules", tags=["radio"])


class ScheduleItemBody(BaseModel):
    kind: str
    beets_id: str | None = None
    item_id: str | None = None


class ScheduleSessionBody(BaseModel):
    kind: str
    title: str
    starts_at: str | None = None
    note: str | None = None
    items: list[ScheduleItemBody]


class ScheduleBody(BaseModel):
    note: str | None = None
    sessions: list[ScheduleSessionBody]


def _service(request: Request) -> RadioScheduleService:
    return request.app.state.radio_schedule_service  # type: ignore[no-any-return]


def _input(body: ScheduleBody) -> ScheduleInput:
    return ScheduleInput(
        note=body.note,
        sessions=[
            ScheduleSessionInput(
                kind=session.kind,
                title=session.title,
                starts_at=session.starts_at,
                note=session.note,
                items=[
                    ScheduleItemInput(kind=item.kind, beets_id=item.beets_id, item_id=item.item_id)
                    for item in session.items
                ],
            )
            for session in body.sessions
        ],
    )


@router.get("")
def schedules(request: Request) -> list[ScheduleSummary]:
    return _service(request).list()


@router.get("/{schedule_date}")
def schedule(schedule_date: date, request: Request) -> ScheduleView:
    result = _service(request).get(schedule_date)
    if result is None:
        raise HTTPException(status_code=404, detail="No schedule for this date")
    return result


@router.put("/{schedule_date}")
def replace_schedule(schedule_date: date, body: ScheduleBody, request: Request) -> ScheduleView:
    try:
        return _service(request).replace(schedule_date, _input(body))
    except ScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
