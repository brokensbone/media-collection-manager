from fastapi import APIRouter, Request

from ..adapters.album_repo import AlbumSummary

router = APIRouter(tags=["library"])


@router.get("/albums")
def list_albums(request: Request, state: str | None = None) -> list[AlbumSummary]:
    return request.app.state.album_repo.list_albums(state)  # type: ignore[no-any-return]
