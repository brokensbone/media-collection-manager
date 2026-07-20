from dataclasses import asdict

from fastapi import APIRouter, Request

from ..adapters.album_repo import TransmissionRow
from ..transmission_service import ConnectionReport, TransmissionService

router = APIRouter(prefix="/transmission", tags=["transmission"])


def _service(request: Request) -> TransmissionService:
    return request.app.state.transmission_service  # type: ignore[no-any-return]


@router.get("/torrents")
def torrents(request: Request) -> list[TransmissionRow]:
    return _service(request).torrents()


@router.post("/test")
def test(request: Request) -> dict[str, dict[str, object]]:
    report: ConnectionReport = _service(request).test()
    return {"api": asdict(report.api), "ssh": asdict(report.ssh)}
