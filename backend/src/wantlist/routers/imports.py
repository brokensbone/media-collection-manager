from fastapi import APIRouter, Request

from ..imports import ImportItem, ImportsService

router = APIRouter(tags=["imports"])


def _service(request: Request) -> ImportsService:
    return request.app.state.imports_service  # type: ignore[no-any-return]


@router.get("/imports")
def import_queue(request: Request) -> list[ImportItem]:
    return _service(request).queue()


@router.post("/imports/{import_id}/import", status_code=204)
def run_import(import_id: int, request: Request) -> None:
    _service(request).enqueue(import_id)  # queued; the worker imports it in the background
