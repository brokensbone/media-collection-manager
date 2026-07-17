from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..acquire import AcquireItem, AcquireService
from ..library_assist import LinkCandidate

router = APIRouter(tags=["acquire"])


class MarkOwnedBody(BaseModel):
    beets_id: str | None = None  # a chosen library album to link (D17), or None = link-less


def _service(request: Request) -> AcquireService:
    return request.app.state.acquire_service  # type: ignore[no-any-return]


@router.get("/acquire")
def acquire_queue(request: Request) -> list[AcquireItem]:
    return _service(request).queue()


@router.get("/albums/{album_id}/link-candidates")
def link_candidates(album_id: int, request: Request) -> list[LinkCandidate]:
    return _service(request).link_candidates(album_id)


@router.post("/albums/{album_id}/order", status_code=204)
def order(album_id: int, request: Request) -> None:
    _service(request).mark_ordered(album_id)


@router.post("/albums/{album_id}/unorder", status_code=204)
def unorder(album_id: int, request: Request) -> None:
    _service(request).cancel_order(album_id)


@router.post("/albums/{album_id}/mark-owned", status_code=204)
def mark_owned(album_id: int, request: Request, body: MarkOwnedBody | None = None) -> None:
    _service(request).mark_owned(album_id, (body or MarkOwnedBody()).beets_id)
