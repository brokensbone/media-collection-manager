from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from ..adapters.album_repo import TransmissionRow
from ..transmission_service import ConnectionReport, TransmissionService

router = APIRouter(prefix="/transmission", tags=["transmission"])


def _service(request: Request) -> TransmissionService:
    return request.app.state.transmission_service  # type: ignore[no-any-return]


@router.get("/torrents")
def torrents(request: Request) -> list[TransmissionRow]:
    return _service(request).torrents()


@router.post("/torrents")
async def add_torrent(request: Request, file: Annotated[UploadFile, File()]) -> dict[str, str]:
    if not file.filename or not file.filename.lower().endswith(".torrent"):
        raise HTTPException(status_code=400, detail="Choose a .torrent file.")

    metainfo = await file.read()
    if not metainfo:
        raise HTTPException(status_code=400, detail="The torrent file is empty.")
    if len(metainfo) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Torrent files must be 2 MiB or smaller.")

    try:
        _service(request).add_torrent(metainfo)
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Transmission rejected the torrent: {e}"
        ) from e
    return {"detail": "Torrent added to Transmission."}


@router.post("/test")
def test(request: Request) -> dict[str, dict[str, object]]:
    report: ConnectionReport = _service(request).test()
    return {"api": asdict(report.api), "ssh": asdict(report.ssh)}
