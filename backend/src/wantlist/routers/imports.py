from fastapi import APIRouter, Request

from ..imports import DetectResult, ImportItem, ImportsService, WatchdirDetectionService

router = APIRouter(tags=["imports"])


def _service(request: Request) -> ImportsService:
    return request.app.state.imports_service  # type: ignore[no-any-return]


def _watchdir(request: Request) -> WatchdirDetectionService:
    return request.app.state.watchdir_detection_service  # type: ignore[no-any-return]


@router.get("/imports")
def import_queue(request: Request) -> list[ImportItem]:
    """The Import worklist: downloads awaiting an Import/Discard decision."""
    return _service(request).pending()


@router.get("/imports/tasks")
def import_tasks(request: Request) -> list[ImportItem]:
    """Acted-on imports: in progress, queued, failed, plus recently completed."""
    days = request.app.state.settings.import_completed_window_days
    return _service(request).tasks(completed_window_days=days)


@router.get("/imports/archive")
def import_archive(request: Request) -> list[ImportItem]:
    """Every completed import, however old (reached from the Tasks view)."""
    return _service(request).archive()


@router.post("/imports/scan")
def scan_imports(request: Request) -> DetectResult:
    return _watchdir(request).poll(force=True)


@router.post("/imports/{import_id}/import", status_code=204)
def run_import(import_id: int, request: Request) -> None:
    _service(request).enqueue(import_id)  # queued; the worker imports it in the background


@router.delete("/imports/{import_id}", status_code=204)
def discard_import(import_id: int, request: Request) -> None:
    _service(request).discard(import_id)  # sticky: kept as dismissed so it isn't re-detected
