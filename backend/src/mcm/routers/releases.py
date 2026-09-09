from fastapi import APIRouter, Request

from ..adapters.album_repo import SuggestedRow
from ..releases import ReleasesService

router = APIRouter(tags=["releases"])


def _service(request: Request) -> ReleasesService:
    return request.app.state.releases_service  # type: ignore[no-any-return]


@router.get("/releases")
def releases(request: Request) -> list[SuggestedRow]:
    return _service(request).queue()


@router.post("/albums/{album_id}/save", status_code=204)
def save(album_id: int, request: Request) -> None:
    _service(request).save(album_id)


@router.post("/albums/{album_id}/want", status_code=204)
def want(album_id: int, request: Request) -> None:
    _service(request).want(album_id)


@router.post("/albums/{album_id}/dismiss", status_code=204)
def dismiss(album_id: int, request: Request) -> None:
    _service(request).dismiss(album_id)
