from collections.abc import Iterable

import pytest
from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.adapters.beets import BeetsAlbum
from wantlist.adapters.box_repo import BoxRepo
from wantlist.crates import BoxNotEmpty, CrateError, CrateService, SplitCandidate
from wantlist.library_assist import LibraryAssistService

from .fakes import StubLibraryCatalog


def _svc(
    sf: sessionmaker[Session], catalog: Iterable[BeetsAlbum], *, soft_cap: int = 50
) -> CrateService:
    library = LibraryAssistService(repo=AlbumRepo(sf), catalog=StubLibraryCatalog(catalog))
    return CrateService(repo=BoxRepo(sf), library=library, soft_cap=soft_cap)


def _two_records() -> list[BeetsAlbum]:
    return [BeetsAlbum("b1", "A", "One", None), BeetsAlbum("b2", "B", "Two", None)]


def test_root_holds_every_record_by_default(clean_album_tables: sessionmaker[Session]) -> None:
    view = _svc(clean_album_tables, _two_records()).view(None)
    assert view.name == "Collection" and view.parent_id is None
    assert view.loose_count == 2 and view.total_count == 2
    assert {r.beets_id for r in view.records} == {"b1", "b2"}
    assert [c.id for c in view.breadcrumb] == [view.id]  # root alone


def test_file_down_moves_a_record_into_a_child(clean_album_tables: sessionmaker[Session]) -> None:
    svc = _svc(clean_album_tables, _two_records())
    root = svc.view(None)
    child = svc.create_box(name="Electronic", parent_id=root.id)
    svc.file_down(root.id, ["b1"], child_box_id=child.id)

    root_after = svc.view(None)
    assert root_after.loose_count == 1  # b2 stays loose in root
    assert root_after.total_count == 2  # b1 still counts in the subtree
    assert [(c.loose_count, c.total_count) for c in root_after.children] == [(1, 1)]

    child_view = svc.view(child.id)
    assert {r.beets_id for r in child_view.records} == {"b1"}
    assert [c.name for c in child_view.breadcrumb] == ["Collection", "Electronic"]


def test_file_down_can_create_the_target_box(clean_album_tables: sessionmaker[Session]) -> None:
    svc = _svc(clean_album_tables, _two_records())
    root = svc.view(None)
    child = svc.file_down(root.id, ["b1", "b2"], new_box_name="Mixtapes")
    assert child.name == "Mixtapes"
    assert svc.view(child.id).loose_count == 2


def test_kick_up_returns_a_record_to_the_parent(
    clean_album_tables: sessionmaker[Session],
) -> None:
    svc = _svc(clean_album_tables, _two_records())
    root = svc.view(None)
    child = svc.create_box(name="Electronic", parent_id=root.id)
    svc.file_down(root.id, ["b1"], child_box_id=child.id)

    svc.kick_up(child.id, ["b1"])
    assert svc.view(child.id).loose_count == 0
    assert svc.view(None).loose_count == 2


def test_delete_blocked_when_the_box_has_sub_boxes(
    clean_album_tables: sessionmaker[Session],
) -> None:
    svc = _svc(clean_album_tables, _two_records())
    root = svc.view(None)
    parent = svc.create_box(name="Electronic", parent_id=root.id)
    svc.create_box(name="Dubstep", parent_id=parent.id)
    with pytest.raises(BoxNotEmpty):
        svc.delete_box(parent.id)


def test_deleting_a_leaf_tips_its_records_up_to_the_parent(
    clean_album_tables: sessionmaker[Session],
) -> None:
    svc = _svc(clean_album_tables, _two_records())
    root = svc.view(None)
    outer = svc.create_box(name="Electronic", parent_id=root.id)
    inner = svc.create_box(name="Dubstep", parent_id=outer.id)
    # File b1 one level at a time (kick distance 1): root → outer → inner.
    svc.file_down(root.id, ["b1"], child_box_id=outer.id)
    svc.file_down(outer.id, ["b1"], child_box_id=inner.id)

    svc.delete_box(inner.id)
    assert svc.view(outer.id).loose_count == 1  # b1 tipped up into its parent, not the root
    assert svc.view(None).loose_count == 1  # only b2 remains loose in root


def test_root_cannot_be_deleted_or_kicked_up(clean_album_tables: sessionmaker[Session]) -> None:
    svc = _svc(clean_album_tables, _two_records())
    root = svc.view(None)
    with pytest.raises(CrateError):
        svc.delete_box(root.id)
    with pytest.raises(CrateError):
        svc.kick_up(root.id, ["b1"])


def test_file_down_rejects_a_non_direct_child(clean_album_tables: sessionmaker[Session]) -> None:
    svc = _svc(clean_album_tables, _two_records())
    root = svc.view(None)
    outer = svc.create_box(name="Electronic", parent_id=root.id)
    grand = svc.create_box(name="Dubstep", parent_id=outer.id)
    # grand is two levels below root — kick distance is 1, so this must be rejected.
    with pytest.raises(CrateError):
        svc.file_down(root.id, ["b1"], child_box_id=grand.id)


def test_over_cap_is_flagged_on_the_loose_count(
    clean_album_tables: sessionmaker[Session],
) -> None:
    svc = _svc(clean_album_tables, _two_records(), soft_cap=1)
    view = svc.view(None)
    assert view.soft_cap == 1 and view.over_cap is True


def test_a_move_only_touches_records_actually_in_the_source_box(
    clean_album_tables: sessionmaker[Session],
) -> None:
    svc = _svc(clean_album_tables, _two_records())
    root = svc.view(None)
    child = svc.create_box(name="Electronic", parent_id=root.id)
    # b2 isn't in the catalog's source box selection cleanly: ask to file b1 plus a phantom id.
    svc.file_down(root.id, ["b1", "ghost"], child_box_id=child.id)
    assert {r.beets_id for r in svc.view(child.id).records} == {"b1"}
    # b1 is now in the child; a stale attempt to file it again *from root* is a no-op.
    svc.file_down(root.id, ["b1"], child_box_id=child.id)
    assert svc.view(child.id).loose_count == 1


def test_rename_box(clean_album_tables: sessionmaker[Session]) -> None:
    svc = _svc(clean_album_tables, _two_records())
    root = svc.view(None)
    child = svc.create_box(name="Electronic", parent_id=root.id)
    svc.rename_box(child.id, "Techno")
    assert svc.view(child.id).name == "Techno"


# --- suggested splits (crates §4) --------------------------------------------------------


def _album(
    bid: str,
    *,
    year: int | None = None,
    media: str | None = None,
    label: str | None = None,
    country: str | None = None,
    types: str | None = None,
    genre: str | None = None,
) -> BeetsAlbum:
    return BeetsAlbum(
        beets_id=bid,
        artist="A",
        title=bid,
        mb_releasegroup_id=None,
        year=year,
        media=media,
        label=label,
        country=country,
        secondary_types=types,
        genre=genre,
    )


def _by_key(candidates: list[SplitCandidate]) -> dict[str, SplitCandidate]:
    return {c.key: c for c in candidates}


def test_decade_facet_buckets_years_into_decades(
    clean_album_tables: sessionmaker[Session],
) -> None:
    catalog = [_album(f"y{i}", year=2007) for i in range(3)] + [
        _album(f"z{i}", year=2013) for i in range(3)
    ]
    svc = _svc(clean_album_tables, catalog)
    cand = _by_key(svc.suggest_splits(svc.view(None).id))["decade"]
    assert cand.label == "Decade"
    assert [(g.name, g.count) for g in cand.groups] == [("2000s", 3), ("2010s", 3)]
    assert cand.covers == 6 and cand.leaves == 0


def test_groups_below_the_minimum_are_dropped_and_left_loose(
    clean_album_tables: sessionmaker[Session],
) -> None:
    # CD and vinyl each clear MIN_GROUP; the 2 cassettes fall short and stay loose.
    catalog = (
        [_album(f"c{i}", media="CD") for i in range(4)]
        + [_album(f"v{i}", media="12″ Vinyl") for i in range(4)]
        + [_album(f"t{i}", media="Cassette") for i in range(2)]
    )
    svc = _svc(clean_album_tables, catalog)
    cand = _by_key(svc.suggest_splits(svc.view(None).id))["format"]
    assert [(g.name, g.count) for g in cand.groups] == [("12″ Vinyl", 4), ("CD", 4)]
    assert cand.covers == 8 and cand.leaves == 2


def test_type_facet_maps_secondary_types_and_ignores_studio_albums(
    clean_album_tables: sessionmaker[Session],
) -> None:
    catalog = [_album(f"m{i}", types="Album; DJ-mix") for i in range(3)] + [
        _album(f"c{i}", types="Album; Compilation") for i in range(3)
    ]
    # A plain studio album has only the primary type — no split value.
    catalog += [_album("plain", types="Album")]
    svc = _svc(clean_album_tables, catalog)
    cand = _by_key(svc.suggest_splits(svc.view(None).id))["type"]
    assert {(g.name, g.count) for g in cand.groups} == {("Mixtapes", 3), ("Compilations", 3)}
    assert cand.leaves == 1  # the studio album stays loose


def test_a_single_dominant_group_is_penalised_out(
    clean_album_tables: sessionmaker[Session],
) -> None:
    # Only one label clears MIN_GROUP, so the "split" is really a lone extraction: the single-group
    # card factor plus the dominance penalty keep it at 0.2, below the strict surfacing threshold.
    catalog = [_album(f"big{i}", label="Big") for i in range(20)] + [_album("bare")]
    svc = _svc(clean_album_tables, catalog)
    assert "label" not in _by_key(svc.suggest_splits(svc.view(None).id))


def test_no_facet_has_a_group_yields_no_suggestions(
    clean_album_tables: sessionmaker[Session],
) -> None:
    svc = _svc(clean_album_tables, _two_records())  # two bare records, no facet values
    assert svc.suggest_splits(svc.view(None).id) == []


def test_apply_split_files_records_into_per_value_sub_boxes(
    clean_album_tables: sessionmaker[Session],
) -> None:
    catalog = [_album(f"y{i}", year=2007) for i in range(3)] + [
        _album(f"z{i}", year=2013) for i in range(3)
    ]
    svc = _svc(clean_album_tables, catalog)
    root_id = svc.view(None).id
    view = svc.apply_split(root_id, "decade")

    assert view.loose_count == 0
    by_name = {c.name: c for c in view.children}
    assert by_name["2000s"].total_count == 3 and by_name["2010s"].total_count == 3


def test_apply_split_is_idempotent_on_child_name(
    clean_album_tables: sessionmaker[Session],
) -> None:
    catalog = [_album(f"y{i}", year=2007) for i in range(3)]
    svc = _svc(clean_album_tables, catalog)
    root_id = svc.view(None).id
    svc.apply_split(root_id, "decade")
    svc.apply_split(root_id, "decade")  # a second run must not create a duplicate "2000s"

    view = svc.view(root_id)
    assert [c.name for c in view.children] == ["2000s"]


def test_apply_split_rejects_an_unknown_facet(
    clean_album_tables: sessionmaker[Session],
) -> None:
    svc = _svc(clean_album_tables, _two_records())
    with pytest.raises(CrateError):
        svc.apply_split(svc.view(None).id, "nonsense")
