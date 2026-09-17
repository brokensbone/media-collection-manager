from fastapi import APIRouter, HTTPException, Query, Request

from ..radio_catalogue import RadioAlbum, RadioTrack

router = APIRouter(prefix="/radio", tags=["radio"])


@router.get("/albums")
def albums(
    request: Request,
    genre: str | None = None,
    seed: str = "mcm-radio",
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RadioAlbum]:
    return request.app.state.radio_catalogue_service.albums(  # type: ignore[no-any-return]
        genre=genre, seed=seed, limit=limit
    )


@router.get("/albums/recent")
def recent_albums(
    request: Request, limit: int = Query(default=50, ge=1, le=200)
) -> list[RadioAlbum]:
    return request.app.state.radio_catalogue_service.recent_albums(limit=limit)  # type: ignore[no-any-return]


@router.get("/albums/{beets_id}/tracks")
def album_tracks(request: Request, beets_id: str) -> list[RadioTrack]:
    tracks = request.app.state.radio_catalogue_service.tracks(beets_id)  # type: ignore[no-any-return]
    if not tracks:
        raise HTTPException(status_code=404, detail="No playable tracks for this cached album")
    return tracks


@router.get("/status")
def status(request: Request) -> dict[str, object]:
    return {"catalogue_refreshed_at": request.app.state.radio_catalogue_service.refreshed_at()}
