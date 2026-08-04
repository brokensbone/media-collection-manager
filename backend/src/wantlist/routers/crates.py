from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..adapters.box_repo import BoxRow
from ..crates import BoxNotEmpty, BoxView, CrateError, CrateService, SplitCandidate

router = APIRouter(tags=["crates"])


class CreateBoxBody(BaseModel):
    name: str
    parent_id: int


class RenameBoxBody(BaseModel):
    name: str


class KickUpBody(BaseModel):
    beets_ids: list[str]


class FileDownBody(BaseModel):
    beets_ids: list[str]
    child_box_id: int | None = None  # an existing direct sub-box
    new_box_name: str | None = None  # or create+file into a fresh sub-box in one call


class SplitBody(BaseModel):
    facet: str


def _service(request: Request) -> CrateService:
    return request.app.state.crate_service  # type: ignore[no-any-return]


def _guard[T](fn: Callable[[], T]) -> T:
    """Turn crate-domain errors into HTTP: a blocked delete is 409, anything else a bad request."""
    try:
        return fn()
    except BoxNotEmpty as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except CrateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/crates/box")
def root_box(request: Request) -> BoxView:
    """The crates entry point: the root Collection's view."""
    return _guard(lambda: _service(request).view(None))


@router.get("/crates/box/{box_id}")
def box(box_id: int, request: Request) -> BoxView:
    return _guard(lambda: _service(request).view(box_id))


@router.post("/crates/box")
def create_box(body: CreateBoxBody, request: Request) -> BoxRow:
    return _guard(lambda: _service(request).create_box(name=body.name, parent_id=body.parent_id))


@router.patch("/crates/box/{box_id}", status_code=204)
def rename_box(box_id: int, body: RenameBoxBody, request: Request) -> None:
    _guard(lambda: _service(request).rename_box(box_id, body.name))


@router.delete("/crates/box/{box_id}", status_code=204)
def delete_box(box_id: int, request: Request) -> None:
    _guard(lambda: _service(request).delete_box(box_id))


@router.post("/crates/box/{box_id}/kick-up", status_code=204)
def kick_up(box_id: int, body: KickUpBody, request: Request) -> None:
    _guard(lambda: _service(request).kick_up(box_id, body.beets_ids))


@router.post("/crates/box/{box_id}/file")
def file_down(box_id: int, body: FileDownBody, request: Request) -> BoxRow:
    return _guard(
        lambda: _service(request).file_down(
            box_id,
            body.beets_ids,
            child_box_id=body.child_box_id,
            new_box_name=body.new_box_name,
        )
    )


@router.get("/crates/box/{box_id}/split-suggestions")
def split_suggestions(box_id: int, request: Request) -> list[SplitCandidate]:
    """Ranked ways to divide this box's loose records into sub-boxes (crates §4)."""
    return _guard(lambda: _service(request).suggest_splits(box_id))


@router.post("/crates/box/{box_id}/split")
def apply_split(box_id: int, body: SplitBody, request: Request) -> BoxView:
    return _guard(lambda: _service(request).apply_split(box_id, body.facet))
