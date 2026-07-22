from fastapi import APIRouter, Request

from ..adapters.event_log import EventRow

router = APIRouter(tags=["events"])


@router.get("/events")
def events(request: Request, after: int | None = None, limit: int = 100) -> list[EventRow]:
    """Activity feed the worker writes as it processes items (§16). Poll with `after=<last id>`
    for new rows; omit `after` for the latest page. Always ascending by id."""
    limit = max(1, min(limit, 500))
    return request.app.state.event_log.recent(after=after, limit=limit)  # type: ignore[no-any-return]
