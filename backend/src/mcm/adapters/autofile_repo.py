from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from ..crates import CrateError
from ..models import AutofileRun, BeetsAlbumCache, Box, RecordBox


@dataclass
class RunView:
    id: int
    beets_id: str
    trigger: str
    status: str
    source_box_id: int
    destination_box_id: int | None
    prompt_version: str
    model: str
    album: dict[str, Any]
    evidence: dict[str, Any]
    request: dict[str, Any]
    response: dict[str, Any]
    result: dict[str, Any]
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    resolved_at: datetime | None


def view(row: AutofileRun) -> RunView:
    return RunView(**{name: getattr(row, name) for name in RunView.__dataclass_fields__})


class AutofileConflict(CrateError):
    pass


class AutofileRepo:
    def __init__(self, sf: sessionmaker[Session]) -> None:
        self._sf = sf

    def start(self, **values: Any) -> RunView:
        with self._sf() as session:
            row = AutofileRun(**values)
            session.add(row)
            session.commit()
            return view(row)

    def finish(self, run_id: int, *, completed: bool = True, **values: Any) -> RunView:
        with self._sf() as session:
            row = session.get(AutofileRun, run_id)
            assert row is not None
            for name, value in values.items():
                setattr(row, name, value)
            if completed:
                row.completed_at = datetime.now(UTC)
            session.commit()
            return view(row)

    def get(self, run_id: int) -> RunView:
        with self._sf() as session:
            row = session.get(AutofileRun, run_id)
            if row is None:
                raise CrateError("No such autofile result")
            return view(row)

    def history(self, beets_id: str, limit: int = 50) -> list[RunView]:
        with self._sf() as session:
            return [
                view(row)
                for row in session.scalars(
                    select(AutofileRun)
                    .where(AutofileRun.beets_id == beets_id)
                    .order_by(AutofileRun.id.desc())
                    .limit(limit)
                )
            ]

    def dismiss(self, run_id: int) -> tuple[RunView, bool]:
        with self._sf() as session:
            row = session.scalar(
                select(AutofileRun).where(AutofileRun.id == run_id).with_for_update()
            )
            if row is None:
                raise CrateError("No such autofile result")
            if row.status == "dismissed":
                return view(row), False
            if row.status not in ("suggested", "review", "failed"):
                raise AutofileConflict("This result can no longer be dismissed")
            row.status = "dismissed"
            row.resolved_at = datetime.now(UTC)
            session.commit()
            return view(row), True

    def accept(self, run_id: int, cap: int) -> tuple[RunView, bool]:
        """Move and resolve the suggestion in ONE transaction; serialize competing accepts."""
        with self._sf() as session:
            row = session.scalar(
                select(AutofileRun).where(AutofileRun.id == run_id).with_for_update()
            )
            if row is None:
                raise CrateError("No such autofile result")
            if row.status == "accepted":
                return view(row), False
            if row.status != "suggested" or row.destination_box_id is None:
                raise AutofileConflict("This result has no move to accept")
            boxes = list(session.scalars(select(Box).order_by(Box.id).with_for_update()))
            tree = [{"id": b.id, "name": b.name, "parent_id": b.parent_id} for b in boxes]
            if tree != row.result["tree"]:
                raise AutofileConflict("The crate hierarchy changed. Please run Autofile again.")
            root = next(b for b in boxes if b.parent_id is None)
            membership = session.get(RecordBox, row.beets_id, with_for_update=True)
            current = membership.box_id if membership else root.id
            album = session.get(BeetsAlbumCache, row.beets_id)
            if (
                current != row.source_box_id
                or album is None
                or album.artist != row.album["artist"]
                or album.title != row.album["title"]
            ):
                raise AutofileConflict("The album moved or left the library. Run Autofile again.")
            if any(b.parent_id == row.destination_box_id for b in boxes):
                raise AutofileConflict("The destination is no longer a leaf crate")
            if current == row.destination_box_id:
                raise AutofileConflict("The album is already in that crate")
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(BeetsAlbumCache)
                    .join(RecordBox, RecordBox.beets_id == BeetsAlbumCache.beets_id)
                    .where(RecordBox.box_id == row.destination_box_id)
                )
                or 0
            )
            if count >= cap:
                raise AutofileConflict(f"The destination has reached its {cap}-album limit")
            session.execute(
                insert(RecordBox)
                .values(beets_id=row.beets_id, box_id=row.destination_box_id)
                .on_conflict_do_update(
                    index_elements=["beets_id"], set_={"box_id": row.destination_box_id}
                )
            )
            row.status = "accepted"
            row.resolved_at = datetime.now(UTC)
            session.commit()
            return view(row), True
