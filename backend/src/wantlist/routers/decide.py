from fastapi import APIRouter, Request

from ..decide import DecideItem, DecideService

router = APIRouter(tags=["decide"])


def _service(request: Request) -> DecideService:
    return request.app.state.decide_service  # type: ignore[no-any-return]


@router.get("/decide")
def decide_queue(request: Request) -> list[DecideItem]:
    return _service(request).queue()


@router.post("/albums/{album_id}/keep", status_code=204)
def keep(album_id: int, request: Request) -> None:
    _service(request).keep(album_id)


@router.post("/albums/{album_id}/drop", status_code=204)
def drop(album_id: int, request: Request) -> None:
    _service(request).drop(album_id)


@router.post("/albums/{album_id}/snooze", status_code=204)
def snooze(album_id: int, request: Request) -> None:
    _service(request).snooze(album_id)
