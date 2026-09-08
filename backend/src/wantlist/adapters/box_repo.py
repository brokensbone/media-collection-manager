from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from ..models import Box, RecordBox

_ROOT_NAME = "Collection"


@dataclass
class BoxRow:
    id: int
    name: str
    parent_id: int | None


class BoxRepo:
    """Persistence for crate boxes and record membership (crates §2). The tree lives in `box`;
    membership in `record_box`, keyed by beets id (absence = the root, see the model)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def root(self) -> BoxRow:
        """The root box, get-or-created. The migration seeds "Collection" in prod; this makes the
        root self-healing (and lets tests that build the schema directly skip the seed)."""
        with self._sf() as session:
            row = session.scalars(
                select(Box).where(Box.parent_id.is_(None)).order_by(Box.id)
            ).first()
            if row is None:
                row = Box(name=_ROOT_NAME, parent_id=None)
                session.add(row)
                session.commit()
                session.refresh(row)
            return BoxRow(row.id, row.name, row.parent_id)

    def list_boxes(self) -> list[BoxRow]:
        with self._sf() as session:
            rows = session.execute(select(Box.id, Box.name, Box.parent_id).order_by(Box.id))
            return [BoxRow(*r) for r in rows]

    def get(self, box_id: int) -> BoxRow | None:
        with self._sf() as session:
            row = session.get(Box, box_id)
            return BoxRow(row.id, row.name, row.parent_id) if row else None

    def child_count(self, box_id: int) -> int:
        with self._sf() as session:
            return int(
                session.scalar(select(func.count()).select_from(Box).where(Box.parent_id == box_id))
                or 0
            )

    def create(self, name: str, parent_id: int) -> BoxRow:
        with self._sf() as session:
            row = Box(name=name, parent_id=parent_id)
            session.add(row)
            session.commit()
            session.refresh(row)
            return BoxRow(row.id, row.name, row.parent_id)

    def rename(self, box_id: int, name: str) -> None:
        with self._sf() as session:
            session.execute(update(Box).where(Box.id == box_id).values(name=name))
            session.commit()

    def delete(self, box_id: int) -> None:
        """Delete a box, first tipping its loose records up to its parent. The caller guarantees
        the box is a childless non-root, so its parent is a real box (§2's delete rule)."""
        with self._sf() as session:
            box = session.get(Box, box_id)
            if box is not None and box.parent_id is not None:
                session.execute(
                    update(RecordBox).where(RecordBox.box_id == box_id).values(box_id=box.parent_id)
                )
            session.execute(delete(Box).where(Box.id == box_id))
            session.commit()

    def membership(self) -> dict[str, int]:
        """beets id → box id for every record that has been explicitly filed. Records absent from
        this map are in the root (see the model)."""
        with self._sf() as session:
            return {
                bid: box_id
                for bid, box_id in session.execute(select(RecordBox.beets_id, RecordBox.box_id))
            }

    def assign(self, beets_ids: list[str], box_id: int) -> None:
        """File records into a box — the storage side of the move verb. Upsert, so a record moving
        between boxes just overwrites its row; the first move of a root record inserts one."""
        if not beets_ids:
            return
        with self._sf() as session:
            session.execute(
                pg_insert(RecordBox)
                .values([{"beets_id": bid, "box_id": box_id} for bid in beets_ids])
                .on_conflict_do_update(index_elements=["beets_id"], set_={"box_id": box_id})
            )
            session.commit()
