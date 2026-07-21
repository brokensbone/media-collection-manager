"""End-to-end (SPEC §14): the real app + real Postgres + real bundled beets, with Spotify
and MusicBrainz served by a live stub over the configurable base URLs. Drives the whole
loop — OAuth -> ingest -> reconcile -> verdict -> acquire — plus the re-auth path.

Runs the real adapters/wiring (not port-level fakes): outbound calls are real HTTP to the
stub; the DB and beets are real. Requires Docker (testcontainers) + the bundled beets.
"""

import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from beets.library import Item, Library
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from wantlist.app import create_app
from wantlist.config import Settings
from wantlist.db import make_engine, make_session_factory
from wantlist.jobs import ingest_once, reconcile_once
from wantlist.models import Base

OWNED_RGID = "rg-owned-e2e"
LONG_AGO = "2020-01-01T00:00:00Z"  # so saves are "forgotten" straight away


class _Control:
    fail_refresh = False


def _stub_handler(control: _Control) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:
            pass

        def _json(self, body: dict[str, object], status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def do_POST(self) -> None:  # noqa: N802 — Spotify token endpoint
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode())
            grant = form.get("grant_type", [""])[0]
            if grant == "refresh_token" and control.fail_refresh:
                self._json({"error": "invalid_grant"}, status=400)
                return
            self._json({"access_token": "at", "refresh_token": "rt", "expires_in": 3600})

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            query = parse_qs(urlparse(self.path).query)
            if path == "/v1/me/albums":
                self._json(
                    {
                        "items": [
                            _saved("albO", "Owned One", "OWNEDUPC"),
                            _saved("albW", "Want One", None),
                        ],
                        "next": None,
                    }
                )
            elif path.startswith("/v1/albums/"):
                self._json({"tracks": {"items": []}, "external_ids": {}})
            elif path == "/v1/tracks":
                self._json({"tracks": []})
            elif path == "/v1/me/player/recently-played":
                self._json({"items": []})
            elif path == "/ws/2/release":
                q = query.get("query", [""])[0]
                if "OWNEDUPC" in q:
                    self._json({"releases": [{"release-group": {"id": OWNED_RGID}}]})
                else:
                    self._json({"releases": []})
            elif path in ("/ws/2/recording", "/ws/2/release-group"):
                self._json({"recordings": [], "release-groups": []})
            else:
                self._json({}, status=404)

    return Handler


def _saved(album_id: str, name: str, upc: str | None) -> dict[str, object]:
    album: dict[str, object] = {
        "id": album_id,
        "name": name,
        "artists": [{"name": "Artist"}],
        "external_ids": {"upc": upc} if upc else {},
        "images": [{"url": "http://img", "width": 300}],
        "tracks": {"items": []},
    }
    return {"added_at": LONG_AGO, "album": album}


@pytest.fixture
def stub() -> Iterator[tuple[str, _Control]]:
    control = _Control()
    server = HTTPServer(("127.0.0.1", 0), _stub_handler(control))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", control
    server.shutdown()


@pytest.fixture
def beetsdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "library.db"
    lib = Library(str(db))
    item = Item(album="Owned One", albumartist="Artist", title="t", path=b"/fake/t.flac")
    item.mb_releasegroupid = OWNED_RGID
    lib.add_album([item])
    del lib
    (tmp_path / "config.yaml").write_text(f"library: {db}\ndirectory: {tmp_path}\n")
    # The app runs `beet` with no -c; it reads BEETSDIR to find config.yaml + the library.
    monkeypatch.setenv("BEETSDIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def settings(pg_e2e_url: str, stub: tuple[str, _Control], beetsdir: Path) -> Settings:
    base, _ = stub
    return Settings(
        database_url=pg_e2e_url,
        spotify_client_id="cid",
        spotify_client_secret="secret",
        spotify_accounts_url=base,
        spotify_api_url=f"{base}/v1",
        musicbrainz_url=f"{base}/ws/2",
        musicbrainz_min_interval=0.0,
    )


@pytest.fixture
def pg_e2e_url() -> Iterator[str]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16", driver="psycopg") as pg:
        url = pg.get_connection_url()
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        engine.dispose()
        yield url


def _connect_spotify(client: TestClient) -> None:
    client.get("/auth/spotify/login", follow_redirects=False)
    state = client.cookies["wl_oauth_state"]
    resp = client.get(
        "/auth/spotify/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert resp.status_code in (302, 307)


def test_full_loop(settings: Settings, stub: tuple[str, _Control]) -> None:
    _, control = stub
    app = create_app(settings)
    client = TestClient(app)

    # 1. OAuth
    _connect_spotify(client)
    assert client.get("/auth/spotify/status").json()["connected"] is True

    # 2. ingest saves, 3. resolve + reconcile
    ingest_once(settings)
    reconcile_once(settings)

    albums = {a["title"]: a for a in client.get("/albums").json()}
    assert albums["Owned One"]["owned"] is True  # resolved via barcode -> in beets
    assert albums["Want One"]["owned"] is False  # unresolved -> stays

    # 4. verdict: the un-owned save surfaces in Decide (forgotten), keep -> wanted
    decide = client.get("/decide").json()
    assert [d["title"] for d in decide] == ["Want One"]
    want_id = decide[0]["id"]
    assert client.post(f"/albums/{want_id}/keep").status_code == 204

    # 5. acquire: it shows with a buy link; mark-owned closes it
    acquire = client.get("/acquire").json()
    assert [a["title"] for a in acquire] == ["Want One"]
    assert acquire[0]["bandcamp_url"].startswith("https://bandcamp.com/search?q=")
    assert client.post(f"/albums/{want_id}/mark-owned").status_code == 204

    assert client.get("/dashboard").json()["owned"] == 2

    # 6. re-auth path: expire the token and make refresh fail -> ingest pauses, disconnected
    control.fail_refresh = True
    engine = make_engine(settings.database_url)
    with make_session_factory(engine)() as session:
        session.execute(
            text("UPDATE spotify_auth SET access_expires_at = :past"),
            {"past": datetime.now(UTC) - timedelta(days=1)},
        )
        session.commit()
    engine.dispose()

    ingest_once(settings)  # refresh -> invalid_grant -> ReauthRequired -> paused (no crash)
    assert client.get("/auth/spotify/status").json()["connected"] is False
