import re
from collections.abc import Callable
from dataclasses import dataclass

from .adapters.box_repo import BoxRepo, BoxRow
from .library_assist import LibraryAssistService, OwnedAlbum

MIN_GROUP = 3  # a facet value needs at least this many records to be worth its own sub-box


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


# --- suggested splits (crates §4) ------------------------------------------------------

# MB primary release types (beets' $albumtypes leads with these); a "type" split keys on the
# *secondary* types, so we skip the primary and treat their absence as "a normal studio album".
_PRIMARY_TYPES = frozenset({"album", "single", "ep", "broadcast", "other"})

# Friendly, pluralised box names for the secondary types worth their own crate. MB spells the
# mix type "Mixtape/Street"; splitting on "/" (below) reduces it to "mixtape", which lands here.
_TYPE_NAMES = {
    "dj-mix": "Mixtapes",
    "mixtape": "Mixtapes",
    "compilation": "Compilations",
    "live": "Live",
    "soundtrack": "Soundtracks",
}


def _decade(r: BoxRecord) -> str | None:
    return None if r.year is None else f"{(r.year // 10) * 10}s"


def _type(r: BoxRecord) -> str | None:
    """The box name for a record's secondary type, or None for a plain studio album. beets joins
    types with "; " (and MB names can carry "," or "/"); we take the first *secondary* one, mapping
    recognised types to a friendly plural and otherwise passing the raw type through."""
    if not r.secondary_types:
        return None
    parts = [p.strip() for p in re.split(r"[;,/]", r.secondary_types) if p.strip()]
    secondary = [p for p in parts if p.lower() not in _PRIMARY_TYPES]
    for p in secondary:
        mapped = _TYPE_NAMES.get(p.lower())
        if mapped is not None:
            return mapped
    return secondary[0] if secondary else None


@dataclass(frozen=True)
class Facet:
    """One axis a box can be split along. `value` derives a record's group — which is also the
    name of the sub-box it would be filed into (crates §4)."""

    key: str
    label: str  # human axis name for the UI ("Decade", "Format", …)
    value: Callable[[BoxRecord], str | None]
    # An extraction facet pulls a category *out* (Mixtapes, Compilations…) rather than partitioning
    # the box. That's inherently "one bucket", so it skips the dominance penalty and a lone group
    # still counts — otherwise the flagship "pull out the mixtapes" offer would never surface.
    extraction: bool = False


_FACETS: tuple[Facet, ...] = (
    Facet("decade", "Decade", _decade),
    Facet("format", "Format", lambda r: r.media),
    Facet("type", "Type", _type, extraction=True),
    Facet("label", "Label", lambda r: r.label),
    Facet("country", "Country", lambda r: r.country),
    Facet("genre", "Genre", lambda r: r.genre),
)
_FACET_BY_KEY = {f.key: f for f in _FACETS}


@dataclass
class SplitGroup:
    name: str
    count: int


@dataclass
class SplitCandidate:
    key: str
    label: str
    groups: list[SplitGroup]  # kept groups (count >= MIN_GROUP), sorted by count desc
    covers: int  # records this split would file into sub-boxes
    leaves: int  # records left loose here (no value, or in a sub-MIN group)


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

    def suggest_splits(self, box_id: int) -> list[SplitCandidate]:
        """Rank ways to divide this box's loose records into single-facet sub-boxes (crates §4).
        Each facet's partition is scored on cardinality (2–8 groups is ideal), how big a chunk it
        organises, and whether one value dominates; the strongest few are offered as a preview."""
        if self._repo.get(box_id) is None:
            raise CrateError(f"no such box {box_id}")
        loose = self._loose_records(box_id)
        loose_total = len(loose)

        scored: list[tuple[float, SplitCandidate]] = []
        for facet in _FACETS:
            counts = self._facet_counts(facet, loose)
            kept = {name: n for name, n in counts.items() if n >= MIN_GROUP}
            if not kept:
                continue
            sizes = list(kept.values())
            n = len(kept)
            moved = sum(sizes)
            biggest_frac = max(sizes) / moved
            size_factor = min(1.0, moved / 12)  # rewards organising a real chunk, not the whole box
            if facet.extraction:
                # Extraction: a lone category is fine, and "one bucket" is the whole point — no
                # dominance penalty. So pulling out ~38 mixtapes surfaces near the top.
                card_factor = 1.0 if 1 <= n <= 8 else 0.5 if n <= 15 else 0.2
                score = card_factor * size_factor
            else:
                # Partition: a single group is no split, and one value dominating is a weak divide.
                card_factor = 1.0 if 2 <= n <= 8 else 0.6 if n == 1 else 0.5 if n <= 15 else 0.2
                score = card_factor * size_factor - (0.4 if biggest_frac > 0.85 else 0.0)
            if score <= 0.2:
                continue
            groups = [
                SplitGroup(name=name, count=n_)
                for name, n_ in sorted(kept.items(), key=lambda kv: (-kv[1], kv[0].lower()))
            ]
            scored.append(
                (
                    score,
                    SplitCandidate(
                        key=facet.key,
                        label=facet.label,
                        groups=groups,
                        covers=moved,
                        leaves=loose_total - moved,
                    ),
                )
            )
        scored.sort(key=lambda s: s[0], reverse=True)  # stable: ties keep facet order
        return [c for _, c in scored[:4]]

    def apply_split(self, box_id: int, facet_key: str) -> BoxView:
        """File this box's loose records into per-value sub-boxes along `facet_key` — the bulk form
        of the manual file-down verb (crates §4). Records with no value, or in a sub-MIN group, stay
        loose. Reuses a same-named child if one already exists, so re-applying is idempotent."""
        if self._repo.get(box_id) is None:
            raise CrateError(f"no such box {box_id}")
        facet = _FACET_BY_KEY.get(facet_key)
        if facet is None:
            raise CrateError(f"unknown split facet {facet_key!r}")

        by_value: dict[str, list[str]] = {}
        for r in self._loose_records(box_id):
            v = facet.value(r)
            if v is not None:
                by_value.setdefault(v, []).append(r.beets_id)

        for name, beets_ids in by_value.items():
            if len(beets_ids) < MIN_GROUP:
                continue
            child = self._get_or_create_child(box_id, name)
            self.file_down(box_id, beets_ids, child_box_id=child.id)
        return self.view(box_id)

    # --- internals -------------------------------------------------------------------

    def _loose_records(self, box_id: int) -> list[BoxRecord]:
        root_id = self._repo.root().id  # get-or-create first, so list_boxes includes it
        boxes = {b.id: b for b in self._repo.list_boxes()}
        records = self._library.owned_library()
        effective = self._effective_boxes(records, boxes, root_id)
        return [self._record(r) for r in records if effective.get(r.beets_id) == box_id]

    def _facet_counts(self, facet: Facet, loose: list[BoxRecord]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in loose:
            v = facet.value(r)
            if v is not None:
                counts[v] = counts.get(v, 0) + 1
        return counts

    def _get_or_create_child(self, box_id: int, name: str) -> BoxRow:
        for b in self._repo.list_boxes():
            if b.parent_id == box_id and b.name == name:
                return b
        return self._repo.create(name, box_id)

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
