from fastapi import APIRouter, Request

from ..acquire import AcquireItem, AcquireService

router = APIRouter(tags=["acquire"])


def _service(request: Request) -> AcquireService:
    return request.app.state.acquire_service  # type: ignore[no-any-return]


@router.get("/acquire")
def acquire_queue(request: Request) -> list[AcquireItem]:
    return _service(request).queue()


@router.post("/albums/{album_id}/order", status_code=204)
def order(album_id: int, request: Request) -> None:
    _service(request).mark_ordered(album_id)


@router.post("/albums/{album_id}/unorder", status_code=204)
def unorder(album_id: int, request: Request) -> None:
    _service(request).cancel_order(album_id)


@router.post("/albums/{album_id}/mark-owned", status_code=204)
def mark_owned(album_id: int, request: Request) -> None:
    _service(request).mark_owned(album_id)
