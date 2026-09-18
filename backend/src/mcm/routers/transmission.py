from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from ..adapters.album_repo import TransmissionRow
from ..ports.transmission import AddedTorrent
from ..torrent_submission_service import TorrentSubmissionService
from ..transmission_service import ConnectionReport, TransmissionService

router = APIRouter(prefix="/transmission", tags=["transmission"])


def _service(request: Request) -> TransmissionService:
    return request.app.state.transmission_service  # type: ignore[no-any-return]


def _submission_service(request: Request) -> TorrentSubmissionService:
    return request.app.state.torrent_submission_service  # type: ignore[no-any-return]


@router.get("/torrents")
def torrents(request: Request) -> list[TransmissionRow]:
    return _service(request).torrents()


@router.post("/torrents")
async def add_torrent(
    request: Request, files: Annotated[list[UploadFile], File()]
) -> dict[str, str]:
    metainfos: list[bytes] = []
    for file in files:
        if not file.filename or not file.filename.lower().endswith(".torrent"):
            raise HTTPException(status_code=400, detail="Choose .torrent files only.")

        metainfo = await file.read()
        if not metainfo:
            raise HTTPException(status_code=400, detail="Torrent files cannot be empty.")
        if len(metainfo) > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Torrent files must be 2 MiB or smaller.")
        metainfos.append(metainfo)

    try:
        results = [_submission_service(request).submit(metainfo) for metainfo in metainfos]
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Transmission rejected the torrent: {e}"
        ) from e
    return {"detail": _submission_detail(results)}


def _submission_detail(results: list[AddedTorrent]) -> str:
    """Report the two outcomes separately. Transmission calls both of them success, so a
    plain count of files chosen reads as a count of downloads started, which it is not."""
    already = sum(1 for r in results if r.already_present)
    started = len(results) - already
    if not already:
        return f"{started} torrent{'s' if started != 1 else ''} added to Transmission."
    if not started:
        was = "was" if already == 1 else "were"
        return f"{already} torrent{'s' if already != 1 else ''} {was} already in Transmission."
    was = "was" if already == 1 else "were"
    return (
        f"{started} torrent{'s' if started != 1 else ''} added to Transmission; "
        f"{already} {was} already there."
    )


@router.post("/test")
def test(request: Request) -> dict[str, dict[str, object]]:
    report: ConnectionReport = _service(request).test()
    return {"api": asdict(report.api), "ssh": asdict(report.ssh)}
