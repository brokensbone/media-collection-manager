from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request

from ..radio_catalogue import RadioAlbum, RadioCatalogueService, RadioTrack

router = APIRouter(prefix="/radio", tags=["radio"])


@router.get("/albums")
def albums(
    request: Request,
    genre: str | None = None,
    seed: str = "mcm-radio",
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RadioAlbum]:
    return _service(request).albums(genre=genre, seed=seed, limit=limit)


@router.get("/albums/recent")
def recent_albums(
    request: Request, limit: int = Query(default=50, ge=1, le=200)
) -> list[RadioAlbum]:
    return _service(request).recent_albums(limit=limit)


@router.get("/albums/{beets_id}/tracks")
def album_tracks(request: Request, beets_id: str) -> list[RadioTrack]:
    tracks = _service(request).tracks(beets_id)
    if not tracks:
        raise HTTPException(status_code=404, detail="No playable tracks for this cached album")
    return tracks


@router.get("/status")
def status(request: Request) -> dict[str, object]:
    return {"catalogue_refreshed_at": _service(request).refreshed_at()}


def _service(request: Request) -> RadioCatalogueService:
    return cast(RadioCatalogueService, request.app.state.radio_catalogue_service)
