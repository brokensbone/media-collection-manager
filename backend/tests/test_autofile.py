"""Saved suggestion lifecycle, provider contracts and evidence discovery."""

from copy import deepcopy
from dataclasses import asdict
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mcm.adapters.album_description import BandcampDescriptions, BandcampPage, album_url
from mcm.adapters.album_repo import AlbumRepo
from mcm.adapters.autofile_jev import JevCrateJudge
from mcm.adapters.autofile_repo import AutofileRepo
from mcm.adapters.beets import BeetsAlbum
from mcm.adapters.beets_cache import BeetsCatalogCache
from mcm.adapters.box_repo import BoxRepo
from mcm.adapters.event_log import WorkerEventLog
from mcm.app import create_app
from mcm.autofile import AutofileService
from mcm.config import Settings
from mcm.domain.autofile import NONE, interpret
from mcm.library_assist import LibraryAssistService
from mcm.models import Base


class Judge:
    request: dict[str, Any]
    invalid = False
    fail = False
    abstain = False

    def evaluate(self, request):
        self.request = request
        if self.fail:
            raise RuntimeError("provider secret should never reach audit or UI")
        answers = {}
        for key, q in request["questions"].items():
            selected = NONE if self.abstain else next(iter(q["criteria"]))
            answers[key] = {
                "type": "choice",
                "choice": selected,
                "confidence": 1.0,
                "probabilities": {k: 1.0 if k == selected else 0.0 for k in q["criteria"]},
            }
        if self.invalid:
            answers.pop(next(iter(answers)))
        return {"model": "jev-1.14.0", "answers": answers, "usage": {"input_tokens": 123}}


class Descriptions:
    def lookup(self, album):
        return {
            "sources": [
                {
                    "url": "https://example.bandcamp.com/album/test",
                    "description": "Dub textures",
                    "tags": ["dub"],
                }
            ]
        }


@pytest.fixture(params=["sqlite", "postgres"])
def rig(request):
    if request.param == "postgres":
        sf = request.getfixturevalue("clean_album_tables")
        engine = None
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        sf = sessionmaker(engine)
    cache = BeetsCatalogCache(sf)
    cache.replace(
        [
            BeetsAlbum("new", "Ghost Dubs", "Oblique", None),
            BeetsAlbum("old", "Ghost Dubs", "Damaged", None),
        ]
    )
    boxes = BoxRepo(sf)
    root = boxes.root()
    parent = boxes.create("Reggae & Dub", root.id)
    leaf = boxes.create("Dub", parent.id)
    boxes.assign(["old"], leaf.id)
    judge = Judge()
    events = WorkerEventLog(sf)
    service = AutofileService(
        repo=AutofileRepo(sf),
        boxes=boxes,
        library=LibraryAssistService(repo=AlbumRepo(sf), catalog=cache),
        judge=judge,
        descriptions=Descriptions(),
        events=events,
    )
    app = create_app(Settings())
    app.state.autofile_service = service
    yield service, boxes, cache, judge, events, TestClient(app), root, leaf
    if engine is not None:
        engine.dispose()


def test_saved_suggestion_only_moves_on_accept_and_accept_is_idempotent(rig):
    service, boxes, _, judge, events, client, _, leaf = rig
    response = client.post("/crates/autofile", json={"beets_id": "new"})
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "suggested" and run["destination_box_id"] == leaf.id
    assert "new" not in boxes.membership()
    assert len(judge.request["questions"]) == 2
    assert run["request"] == judge.request and run["response"]["usage"]["input_tokens"] == 123
    assert len(run["result"]["steps"]) == 2 and run["evidence"]["sources"]
    assert client.get(f"/crates/autofile/{run['id']}").json() == run
    assert client.get("/crates/autofile?beets_id=new").json()[0]["id"] == run["id"]
    assert client.post(f"/crates/autofile/{run['id']}/accept").json()["status"] == "accepted"
    assert boxes.membership()["new"] == leaf.id
    assert client.post(f"/crates/autofile/{run['id']}/accept").status_code == 200
    assert [e.type for e in events.recent()].count("autofile_accepted") == 1
    assert service.repo.get(run["id"]).resolved_at is not None


def test_dismiss_keeps_album_and_history(rig):
    service, boxes, _, _, events, client, _, _ = rig
    run = service.suggest("new", trigger="acquisition-test")
    assert client.post(f"/crates/autofile/{run.id}/dismiss").json()["status"] == "dismissed"
    assert client.post(f"/crates/autofile/{run.id}/accept").status_code == 409
    service.dismiss(run.id)
    assert "new" not in boxes.membership()
    assert service.repo.history("new")[0].trigger == "acquisition-test"
    assert [e.type for e in events.recent()].count("autofile_dismissed") == 1


@pytest.mark.parametrize("change", ["moved", "tree", "full", "removed"])
def test_accept_rechecks_live_state(rig, change):
    service, boxes, cache, _, _, client, root, leaf = rig
    run = service.suggest("new")
    if change == "moved":
        boxes.assign(["new"], leaf.id)
    elif change == "tree":
        boxes.create("New category", root.id)
    elif change == "full":
        service._cap = 1
    else:
        cache.replace([BeetsAlbum("old", "Ghost Dubs", "Damaged", None)])
    assert client.post(f"/crates/autofile/{run.id}/accept").status_code == 409
    assert service.repo.get(run.id).status == "suggested"


@pytest.mark.parametrize("mode", ["fail", "invalid", "abstain"])
def test_failure_and_no_fit_are_saved_without_moves(rig, mode):
    service, boxes, _, judge, events, _, _, _ = rig
    setattr(judge, mode, True)
    run = service.suggest("new")
    assert run.status == ("review" if mode == "abstain" else "failed")
    assert service.repo.get(run.id).request
    assert "new" not in boxes.membership()
    assert "secret" not in str(asdict(run))
    assert events.recent()[-1].type in ("error", "autofile_suggested")


def test_full_and_already_filed_results_and_subject_exclusion(rig):
    service, _, _, _, _, _, _, _ = rig
    service._cap = 1
    full = service.suggest("new")
    assert full.status == "review" and "full" in full.result["reason"]
    existing = service.suggest("old")
    assert existing.status == "review" and "already" in existing.result["reason"]
    assert "Ghost Dubs — Damaged" not in str(existing.request)


@pytest.mark.parametrize("value", [float("nan"), -0.1, 1.1, True])
def test_provider_probabilities_must_be_valid(rig, value):
    service, _, _, _, _, _, _, _ = rig
    run = service.suggest("new")
    response = deepcopy(run.response)
    key = next(iter(response["answers"]))
    option = next(iter(response["answers"][key]["probabilities"]))
    response["answers"][key]["probabilities"][option] = value
    with pytest.raises(ValueError):
        interpret(run.request, response, [])


def test_bandcamp_parser_and_safe_urls():
    page = BandcampPage()
    page.feed(
        '<meta property="og:title" content="Oblique, by Ghost Dubs">'
        '<script data-tralbum="{&quot;current&quot;:'
        '{&quot;about&quot;:&quot;Deep dub&quot;}}"></script>'
        '<a class="tag">dub techno</a>'
    )
    assert page.about == "Deep dub" and page.tags == ["dub techno"]
    assert album_url("https://ghostdubs.bandcamp.com/album/oblique?from=search")
    assert album_url("https://evil.example/album/oblique") is None
    assert album_url("http://ghostdubs.bandcamp.com/album/oblique") is None
    assert album_url("https://ghostdubs.bandcamp.com:8443/album/oblique") is None


@respx.mock
def test_description_identity_matching_and_source():
    respx.get("https://bandcamp.com/search").mock(
        return_value=httpx.Response(
            200,
            text='<a href="https://artist.bandcamp.com/album/wrong">Wrong</a>'
            '<a href="https://artist.bandcamp.com/album/right">Right</a>',
        )
    )
    respx.get("https://artist.bandcamp.com/album/wrong").mock(
        return_value=httpx.Response(
            200, text='<meta property="og:title" content="Wrong, by Ghost Dubs">'
        )
    )
    respx.get("https://artist.bandcamp.com/album/right").mock(
        return_value=httpx.Response(
            200,
            text='<meta property="og:title" content="Oblique, by Ghost Dubs">'
            '<script data-tralbum="{&quot;current&quot;:'
            '{&quot;about&quot;:&quot;Deep dub&quot;}}"></script>',
        )
    )
    result = BandcampDescriptions().lookup({"artist": "Ghost Dubs", "title": "Oblique"})
    assert result["sources"][0]["description"] == "Deep dub"
    assert result["sources"][0]["url"].endswith("/right")


@respx.mock
def test_description_failure_is_explicit_metadata_fallback():
    respx.get("https://bandcamp.com/search").mock(return_value=httpx.Response(429))
    respx.get("https://ghostdubs.bandcamp.com/album/oblique").mock(return_value=httpx.Response(404))
    result = BandcampDescriptions().lookup({"artist": "Ghost Dubs", "title": "Oblique"})
    assert result["sources"] == [] and "unavailable" in result["notice"]


@respx.mock
def test_jev_transport_uses_pinned_request_and_keeps_key_out_of_body():
    route = respx.post("https://api.typesafe.ai/v1/systemone").mock(
        return_value=httpx.Response(200, json={"answers": {}})
    )
    JevCrateJudge("private-key").evaluate({"model": "jev-1.14.0", "state": {}, "questions": {}})
    assert route.calls[0].request.headers["authorization"] == "Bearer private-key"
    assert b"private-key" not in route.calls[0].request.content


def test_competing_accepts_do_not_overfill_destination(rig, request):
    from concurrent.futures import ThreadPoolExecutor

    from mcm.adapters.autofile_repo import AutofileConflict

    if request.node.callspec.params["rig"] != "postgres":
        pytest.skip("Row locking is a PostgreSQL contract")
    service, boxes, cache, _, _, _, _, leaf = rig
    cache.replace(
        [
            BeetsAlbum("old", "Ghost Dubs", "Damaged", None),
            BeetsAlbum("new", "Ghost Dubs", "Oblique", None),
            BeetsAlbum("other", "Ghost Dubs", "Other", None),
        ]
    )
    service._cap = 2
    runs = [service.suggest("new"), service.suggest("other")]

    def accept(run):
        try:
            return service.accept(run.id).status
        except AutofileConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(accept, runs))
    assert sorted(outcomes) == ["accepted", "conflict"]
    assert sum(box == leaf.id for box in boxes.membership().values()) == 2


@respx.mock
def test_direct_bandcamp_candidate_is_verified_when_search_has_no_links():
    respx.get("https://bandcamp.com/search").mock(return_value=httpx.Response(200, text="No links"))
    respx.get("https://ghostdubs.bandcamp.com/album/oblique").mock(
        return_value=httpx.Response(
            200,
            text='<meta property="og:title" content="Oblique, by Ghost Dubs">'
            '<script data-tralbum="{&quot;current&quot;:'
            '{&quot;about&quot;:&quot;Deep dub&quot;}}"></script>',
        )
    )
    evidence = BandcampDescriptions().lookup({"artist": "Ghost Dubs", "title": "Oblique"})
    assert evidence["sources"][0]["description"] == "Deep dub"
