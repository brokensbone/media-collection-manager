from fastapi import APIRouter, Request

from ..adapters.album_repo import AlbumSummary
from ..library_assist import OwnedAlbum

router = APIRouter(tags=["library"])


@router.get("/albums")
def list_albums(request: Request, state: str | None = None) -> list[AlbumSummary]:
    return request.app.state.album_repo.list_albums(state)  # type: ignore[no-any-return]


@router.get("/owned")
def owned_library(request: Request) -> list[OwnedAlbum]:
    """The Owned view: the full beets library (what you own), enriched with Spotify where it
    matches — not just the Spotify∩beets overlap that the funnel's `owned` state captures."""
    return request.app.state.library_assist_service.owned_library()  # type: ignore[no-any-return]
