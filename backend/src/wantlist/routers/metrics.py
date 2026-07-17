from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from ..metrics import CONTENT_TYPE, MetricsService

router = APIRouter(tags=["metrics"])


def _service(request: Request) -> MetricsService:
    return request.app.state.metrics_service  # type: ignore[no-any-return]


@router.get("/metrics")
def metrics(request: Request) -> PlainTextResponse:
    return PlainTextResponse(_service(request).render(), media_type=CONTENT_TYPE)
