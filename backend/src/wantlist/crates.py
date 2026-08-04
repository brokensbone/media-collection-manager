from dataclasses import dataclass

from .adapters.box_repo import BoxRepo, BoxRow
from .library_assist import LibraryAssistService, OwnedAlbum


class CrateError(Exception):
    """A rejected crate operation (bad target, root violation) — maps to 400."""


class BoxNotEmpty(CrateError):
    """Delete blocked because the box still has sub-boxes (§2) — maps to 409."""


@dataclass
class Crumb:
    id: int
    name: str


@dataclass
class ChildBox:
    id: int
    name: str
    loose_count: int  # records filed directly in this child
    total_count: int  # records in this child and everything below it


@dataclass
class BoxRecord:
    beets_id: str
    artist: str
    title: str
    album_id: int | None
    has_art: bool
    spotify_id: str | None
    year: int | None
    media: str | None
    label: str | None
    country: str | None
    secondary_types: str | None
    genre: str | None


@dataclass
class BoxView:
    id: int
    name: str
    parent_id: int | None
    breadcrumb: list[Crumb]
    children: list[ChildBox]
    records: list[BoxRecord]  # the loose records here, sorted by artist/title
    loose_count: int
    total_count: int
    soft_cap: int
    over_cap: bool  # loose_count > soft_cap → the UI nudges a split (never a hard gate)


class CrateService:
    """The crates layer over the owned library (crates §2). Boxes form a strict tree; each owned
    record sits in exactly one box (root by default). The single verb is move-one-level: kick a
    record up to its box's parent, or file it down into a direct child."""

    def __init__(self, *, repo: BoxRepo, library: LibraryAssistService, soft_cap: int) -> None:
        self._repo = repo
        self._library = library
        self._soft_cap = soft_cap

    def view(self, box_id: int | None) -> BoxView:
        root_id = self._repo.root().id  # get-or-create first, so list_boxes includes it
        boxes = {b.id: b for b in self._repo.list_boxes()}
        target_id = root_id if box_id is None else box_id
        box = boxes.get(target_id)
        if box is None:
            raise CrateError(f"no such box {target_id}")

        records = self._library.owned_library()
        effective = self._effective_boxes(records, boxes, root_id)
        loose_count, total_count = self._counts(boxes, effective)

        children = [
            ChildBox(
                id=c.id,
                name=c.name,
                loose_count=loose_count.get(c.id, 0),
                total_count=total_count.get(c.id, 0),
            )
            for c in boxes.values()
            if c.parent_id == target_id
        ]
        children.sort(key=lambda c: c.name.lower())

        here = [self._record(r) for r in records if effective.get(r.beets_id) == target_id]
        loose = len(here)
        return BoxView(
            id=box.id,
            name=box.name,
            parent_id=box.parent_id,
            breadcrumb=self._breadcrumb(box, boxes),
            children=children,
            records=here,
            loose_count=loose,
            total_count=total_count.get(target_id, 0),
            soft_cap=self._soft_cap,
            over_cap=loose > self._soft_cap,
        )

    def create_box(self, *, name: str, parent_id: int) -> BoxRow:
        name = name.strip()
        if not name:
            raise CrateError("a box needs a name")
        if self._repo.get(parent_id) is None:
            raise CrateError(f"no such parent box {parent_id}")
        return self._repo.create(name, parent_id)

    def rename_box(self, box_id: int, name: str) -> None:
        name = name.strip()
        if not name:
            raise CrateError("a box needs a name")
        if self._repo.get(box_id) is None:
            raise CrateError(f"no such box {box_id}")
        self._repo.rename(box_id, name)

    def delete_box(self, box_id: int) -> None:
        box = self._repo.get(box_id)
        if box is None:
            raise CrateError(f"no such box {box_id}")
        if box.parent_id is None:
            raise CrateError("the root Collection can't be deleted")
        if self._repo.child_count(box_id) > 0:
            raise BoxNotEmpty("delete the sub-boxes first")
        self._repo.delete(box_id)  # its loose records tip up to the parent

    def kick_up(self, box_id: int, beets_ids: list[str]) -> None:
        """Move records up one level, to their box's parent (§2). The root has no parent."""
        box = self._repo.get(box_id)
        if box is None:
            raise CrateError(f"no such box {box_id}")
        if box.parent_id is None:
            raise CrateError("records in the root Collection have nowhere to go up to")
        self._repo.assign(self._in_box(box_id, beets_ids), box.parent_id)

    def file_down(
        self,
        box_id: int,
        beets_ids: list[str],
        *,
        child_box_id: int | None = None,
        new_box_name: str | None = None,
    ) -> BoxRow:
        """Move records down one level, into a direct child of their box (§2) — an existing child
        (`child_box_id`) or a new one created here (`new_box_name`). Kick distance is 1: the target
        must be an immediate child, so nothing skips a level."""
        if self._repo.get(box_id) is None:
            raise CrateError(f"no such box {box_id}")
        if new_box_name is not None:
            child = self.create_box(name=new_box_name, parent_id=box_id)
        elif child_box_id is not None:
            row = self._repo.get(child_box_id)
            if row is None or row.parent_id != box_id:
                raise CrateError("the target must be a direct sub-box of this box")
            child = row
        else:
            raise CrateError("pick a sub-box or name a new one")
        self._repo.assign(self._in_box(box_id, beets_ids), child.id)
        return child

    # --- internals -------------------------------------------------------------------

    def _in_box(self, box_id: int, beets_ids: list[str]) -> list[str]:
        """Restrict a move to records actually loose in the source box, so a stale selection can't
        drag records that have since moved. Empty selection is a no-op, not an error."""
        root_id = self._repo.root().id  # get-or-create first, so list_boxes includes it
        boxes = {b.id: b for b in self._repo.list_boxes()}
        records = self._library.owned_library()
        effective = self._effective_boxes(records, boxes, root_id)
        wanted = set(beets_ids)
        return [bid for bid, eff in effective.items() if eff == box_id and bid in wanted]

    def _effective_boxes(
        self, records: list[OwnedAlbum], boxes: dict[int, BoxRow], root_id: int
    ) -> dict[str, int]:
        """beets id → the box it effectively sits in: its membership row, or the root when it has
        none (or points at a box that no longer exists — defensive, shouldn't happen)."""
        membership = self._repo.membership()
        eff: dict[str, int] = {}
        for r in records:
            bid = membership.get(r.beets_id, root_id)
            eff[r.beets_id] = bid if bid in boxes else root_id
        return eff

    def _counts(
        self, boxes: dict[int, BoxRow], effective: dict[str, int]
    ) -> tuple[dict[int, int], dict[int, int]]:
        """Per box: loose (direct) count and subtree total. Total rolls each box's loose count up
        through its ancestors, so a parent tile shows everything filed anywhere beneath it."""
        loose: dict[int, int] = {b: 0 for b in boxes}
        for box_id in effective.values():
            loose[box_id] = loose.get(box_id, 0) + 1
        total = dict(loose)
        for box_id, n in loose.items():
            parent = boxes[box_id].parent_id
            while parent is not None:
                total[parent] = total.get(parent, 0) + n
                parent = boxes[parent].parent_id
        return loose, total

    def _breadcrumb(self, box: BoxRow, boxes: dict[int, BoxRow]) -> list[Crumb]:
        chain: list[Crumb] = []
        cur: BoxRow | None = box
        while cur is not None:
            chain.append(Crumb(cur.id, cur.name))
            cur = boxes.get(cur.parent_id) if cur.parent_id is not None else None
        return list(reversed(chain))

    def _record(self, r: OwnedAlbum) -> BoxRecord:
        return BoxRecord(
            beets_id=r.beets_id,
            artist=r.artist,
            title=r.title,
            album_id=r.album_id,
            has_art=r.has_art,
            spotify_id=r.spotify_id,
            year=r.year,
            media=r.media,
            label=r.label,
            country=r.country,
            secondary_types=r.secondary_types,
            genre=r.genre,
        )
