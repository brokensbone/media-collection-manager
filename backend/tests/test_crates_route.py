from collections.abc import Iterable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from wantlist.adapters.album_repo import AlbumRepo
from wantlist.adapters.beets import BeetsAlbum
from wantlist.adapters.box_repo import BoxRepo
from wantlist.app import create_app
from wantlist.config import Settings
from wantlist.crates import CrateService
from wantlist.library_assist import LibraryAssistService

from .fakes import StubLibraryCatalog


def _client(sf: sessionmaker[Session], catalog: Iterable[BeetsAlbum]) -> TestClient:
    app = create_app(Settings())
    library = LibraryAssistService(repo=AlbumRepo(sf), catalog=StubLibraryCatalog(catalog))
    app.state.crate_service = CrateService(repo=BoxRepo(sf), library=library, soft_cap=50)
    return TestClient(app)


def _catalog() -> list[BeetsAlbum]:
    return [BeetsAlbum("b1", "A", "One", None), BeetsAlbum("b2", "B", "Two", None)]


def test_root_box_lists_the_whole_library(clean_album_tables: sessionmaker[Session]) -> None:
    body = _client(clean_album_tables, _catalog()).get("/crates/box").json()
    assert body["name"] == "Collection" and body["parent_id"] is None
    assert body["loose_count"] == 2
    assert {r["beets_id"] for r in body["records"]} == {"b1", "b2"}


def test_create_file_and_descend(clean_album_tables: sessionmaker[Session]) -> None:
    client = _client(clean_album_tables, _catalog())
    root_id = client.get("/crates/box").json()["id"]

    child = client.post("/crates/box", json={"name": "Electronic", "parent_id": root_id}).json()
    resp = client.post(
        f"/crates/box/{root_id}/file", json={"beets_ids": ["b1"], "child_box_id": child["id"]}
    )
    assert resp.status_code == 200

    root_view = client.get("/crates/box").json()
    assert root_view["loose_count"] == 1
    assert root_view["children"][0]["total_count"] == 1

    child_view = client.get(f"/crates/box/{child['id']}").json()
    assert {r["beets_id"] for r in child_view["records"]} == {"b1"}


def test_kick_up_endpoint(clean_album_tables: sessionmaker[Session]) -> None:
    client = _client(clean_album_tables, _catalog())
    root_id = client.get("/crates/box").json()["id"]
    child = client.post("/crates/box", json={"name": "X", "parent_id": root_id}).json()
    client.post(
        f"/crates/box/{root_id}/file", json={"beets_ids": ["b1"], "child_box_id": child["id"]}
    )

    resp = client.post(f"/crates/box/{child['id']}/kick-up", json={"beets_ids": ["b1"]})
    assert resp.status_code == 204
    assert client.get("/crates/box").json()["loose_count"] == 2


def test_delete_with_sub_boxes_is_409(clean_album_tables: sessionmaker[Session]) -> None:
    client = _client(clean_album_tables, _catalog())
    root_id = client.get("/crates/box").json()["id"]
    parent = client.post("/crates/box", json={"name": "P", "parent_id": root_id}).json()
    client.post("/crates/box", json={"name": "C", "parent_id": parent["id"]})

    resp = client.delete(f"/crates/box/{parent['id']}")
    assert resp.status_code == 409


def test_deleting_root_is_400(clean_album_tables: sessionmaker[Session]) -> None:
    client = _client(clean_album_tables, _catalog())
    root_id = client.get("/crates/box").json()["id"]
    assert client.delete(f"/crates/box/{root_id}").status_code == 400


def test_rename_endpoint(clean_album_tables: sessionmaker[Session]) -> None:
    client = _client(clean_album_tables, _catalog())
    root_id = client.get("/crates/box").json()["id"]
    child = client.post("/crates/box", json={"name": "Old", "parent_id": root_id}).json()
    assert client.patch(f"/crates/box/{child['id']}", json={"name": "New"}).status_code == 204
    assert client.get(f"/crates/box/{child['id']}").json()["name"] == "New"


def _decade_catalog() -> list[BeetsAlbum]:
    def yr(bid: str, year: int) -> BeetsAlbum:
        return BeetsAlbum(bid, "A", bid, None, year=year)

    return [yr(f"y{i}", 2007) for i in range(3)] + [yr(f"z{i}", 2013) for i in range(3)]


def test_split_suggestions_endpoint(clean_album_tables: sessionmaker[Session]) -> None:
    client = _client(clean_album_tables, _decade_catalog())
    root_id = client.get("/crates/box").json()["id"]
    body = client.get(f"/crates/box/{root_id}/split-suggestions").json()
    decade = next(c for c in body if c["key"] == "decade")
    assert [(g["name"], g["count"]) for g in decade["groups"]] == [("2000s", 3), ("2010s", 3)]
    assert decade["leaves"] == 0


def test_apply_split_endpoint(clean_album_tables: sessionmaker[Session]) -> None:
    client = _client(clean_album_tables, _decade_catalog())
    root_id = client.get("/crates/box").json()["id"]
    resp = client.post(f"/crates/box/{root_id}/split", json={"facet": "decade"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["loose_count"] == 0
    assert {c["name"] for c in body["children"]} == {"2000s", "2010s"}


def test_apply_split_unknown_facet_is_400(clean_album_tables: sessionmaker[Session]) -> None:
    client = _client(clean_album_tables, _catalog())
    root_id = client.get("/crates/box").json()["id"]
    assert client.post(f"/crates/box/{root_id}/split", json={"facet": "bogus"}).status_code == 400
