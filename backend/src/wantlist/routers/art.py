from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(tags=["art"])


@router.get("/art/{album_id}")
def get_art(album_id: int, request: Request) -> Response:
    art = request.app.state.album_repo.get_art(album_id)
    if art is None:
        raise HTTPException(status_code=404)
    content_type, data = art
    etag = f'"{album_id}-{len(data)}"'  # art is immutable per album
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return Response(
        content=data,
        media_type=content_type,
        headers={"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"},
    )
