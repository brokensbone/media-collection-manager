# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""
D0 reconcile / identity spike (SPEC.md §11).

Measures whether the Spotify -> MusicBrainz -> beets ownership match is good enough to
build on, on real data, before committing the architecture. Standalone: read-only Spotify
+ MusicBrainz + a beets `mb_releasegroupid` dump. No app, no Postgres.

Run:  uv run reconcile_spike.py --help

The two sides are decoupled so they can run on different machines:
  - Spotify + MusicBrainz side runs wherever you can open a browser (needs a Spotify app).
  - beets side is just a dump file exported from wherever the library lives (the server):
        beet list -a -f '$mb_releasegroupid' > owned_rgids.txt
    (albums with no release-group id print a blank line -- kept, so we can measure
    coverage: total lines = owned albums, non-blank = albums carrying a release-group id.)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from collections import Counter
from dataclasses import dataclass, field, asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

SPOTIFY_AUTH = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN = "https://accounts.spotify.com/api/token"
SPOTIFY_API = "https://api.spotify.com/v1"
MB_BASE = "https://musicbrainz.org/ws/2"
SCOPE = "user-library-read"


# --------------------------------------------------------------------------- Spotify auth

def _load_token(cache: Path) -> dict | None:
    if cache.exists():
        return json.loads(cache.read_text())
    return None


def _catch_callback(port: int) -> str:
    code_box: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.urlparse(self.path).query
            code_box.update(urllib.parse.parse_qs(q))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Authorized. You can close this tab and return to the terminal.")

        def log_message(self, *_):  # silence the default logging
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=server.handle_request)
    t.start()
    t.join(timeout=300)
    server.server_close()
    if "code" not in code_box:
        raise SystemExit("Did not receive an auth code within 5 minutes.")
    return code_box["code"][0]


def spotify_token(client_id: str, client_secret: str, redirect: str, cache: Path) -> str:
    cache.parent.mkdir(parents=True, exist_ok=True)
    tok = _load_token(cache)
    now = time.time()
    if tok and tok.get("expires_at", 0) > now + 60:
        return tok["access_token"]

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {"Authorization": f"Basic {basic}"}

    if tok and tok.get("refresh_token"):
        r = httpx.post(SPOTIFY_TOKEN, headers=headers, data={
            "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
        if r.status_code == 200:
            data = r.json()
            tok["access_token"] = data["access_token"]
            tok["expires_at"] = now + data.get("expires_in", 3600)
            tok["refresh_token"] = data.get("refresh_token", tok["refresh_token"])
            cache.write_text(json.dumps(tok))
            return tok["access_token"]

    port = urllib.parse.urlparse(redirect).port or 8888
    params = urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code",
        "redirect_uri": redirect, "scope": SCOPE})
    url = f"{SPOTIFY_AUTH}?{params}"
    print(f"\nOpen this URL and authorize (also opening it in your browser):\n{url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    code = _catch_callback(port)
    r = httpx.post(SPOTIFY_TOKEN, headers=headers, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect})
    r.raise_for_status()
    data = r.json()
    tok = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": now + data.get("expires_in", 3600),
    }
    cache.write_text(json.dumps(tok))
    return tok["access_token"]


# --------------------------------------------------------------------------- Spotify data

@dataclass
class Album:
    spotify_id: str
    artist: str
    title: str
    upc: str | None
    isrcs: list[str] = field(default_factory=list)


def fetch_saved_albums(token: str, max_isrcs: int) -> list[Album]:
    client = httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=30)
    albums: list[Album] = []
    url = f"{SPOTIFY_API}/me/albums?limit=50"
    while url:
        r = client.get(url)
        r.raise_for_status()
        page = r.json()
        for item in page["items"]:
            a = item["album"]
            track_ids = [t["id"] for t in a.get("tracks", {}).get("items", []) if t.get("id")]
            albums.append(Album(
                spotify_id=a["id"],
                artist=", ".join(ar["name"] for ar in a["artists"]),
                title=a["name"],
                upc=a.get("external_ids", {}).get("upc"),
                isrcs=_fetch_isrcs(client, track_ids[:max_isrcs]),
            ))
        url = page.get("next")
    client.close()
    return albums


def _fetch_isrcs(client: httpx.Client, track_ids: list[str]) -> list[str]:
    isrcs: list[str] = []
    for i in range(0, len(track_ids), 50):
        batch = track_ids[i:i + 50]
        r = client.get(f"{SPOTIFY_API}/tracks", params={"ids": ",".join(batch)})
        r.raise_for_status()
        for t in r.json()["tracks"]:
            isrc = (t or {}).get("external_ids", {}).get("isrc")
            if isrc:
                isrcs.append(isrc)
    return isrcs


# ------------------------------------------------------------------- MusicBrainz (cached)

class MB:
    def __init__(self, user_agent: str, cache_dir: Path):
        self.client = httpx.Client(headers={"User-Agent": user_agent}, timeout=30)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last = 0.0
        self.live_requests = 0

    def _get(self, path: str, query: str) -> dict:
        url = f"{MB_BASE}/{path}?{urllib.parse.urlencode({'query': query, 'fmt': 'json', 'limit': 25})}"
        key = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if key.exists():
            return json.loads(key.read_text())
        elapsed = time.time() - self._last  # MusicBrainz asks for <= 1 req/sec
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        r = self.client.get(url)
        self._last = time.time()
        self.live_requests += 1
        r.raise_for_status()
        data = r.json()
        key.write_text(json.dumps(data))
        return data

    def by_barcode(self, upc: str) -> list[str]:
        data = self._get("release", f"barcode:{upc}")
        return [rel["release-group"]["id"] for rel in data.get("releases", [])
                if rel.get("release-group")]

    def by_isrc(self, isrc: str) -> list[str]:
        data = self._get("recording", f"isrc:{isrc}")
        rgids: list[str] = []
        for rec in data.get("recordings", []):
            for rel in rec.get("releases", []):
                if rel.get("release-group"):
                    rgids.append(rel["release-group"]["id"])
        return rgids

    def by_text(self, artist: str, title: str) -> tuple[str | None, int]:
        q = f'artist:"{_esc(artist)}" AND releasegroup:"{_esc(title)}"'
        data = self._get("release-group", q)
        groups = data.get("release-groups", [])
        if not groups:
            return None, 0
        return groups[0]["id"], int(groups[0].get("score", 0))


def _esc(s: str) -> str:
    return s.replace('"', " ").replace(":", " ")


# ------------------------------------------------------------------------------ resolution

@dataclass
class Resolution:
    tier: str  # "barcode" | "isrc" | "text" | "none"
    rgid: str | None
    confidence: float  # 0..1 for isrc (share agreeing); text score/100; 1.0 barcode
    owned: bool = False


def resolve(album: Album, mb: MB, isrc_cap: int, text_min_score: int) -> Resolution:
    if album.upc:
        rgids = mb.by_barcode(album.upc)
        if rgids:
            top, n = Counter(rgids).most_common(1)[0]
            return Resolution("barcode", top, round(n / len(rgids), 2))

    if album.isrcs:
        tally: Counter[str] = Counter()
        queried = 0
        for isrc in album.isrcs[:isrc_cap]:
            for rgid in mb.by_isrc(isrc):
                tally[rgid] += 1
            queried += 1
        if tally:
            top, n = tally.most_common(1)[0]
            return Resolution("isrc", top, round(n / max(queried, 1), 2))

    rgid, score = mb.by_text(album.artist, album.title)
    if rgid and score >= text_min_score:
        return Resolution("text", rgid, round(score / 100, 2))

    return Resolution("none", None, 0.0)


# ----------------------------------------------------------------------------------- beets

def owned_rgids(beets_cmd: str | None, beets_config: str | None,
                owned_file: str | None) -> tuple[set[str], int, int]:
    """Return (set of owned release-group ids, total owned albums, albums carrying an id)."""
    if owned_file:
        lines = Path(owned_file).read_text().splitlines()
    elif beets_cmd:
        cmd = beets_cmd.split() + (["-c", beets_config] if beets_config else []) \
            + ["list", "-a", "-f", "$mb_releasegroupid"]
        lines = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.splitlines()
    else:
        raise SystemExit("Provide --owned-file or --beets-cmd for the beets side.")
    non_blank = [ln.strip() for ln in lines if ln.strip()]
    return set(non_blank), len(lines), len(non_blank)


# ---------------------------------------------------------------------------------- report

def report(albums: list[Album], results: list[Resolution],
           total_owned: int, with_id: int, mb_live: int, out_dir: Path) -> None:
    n = len(albums)
    by_tier = Counter(r.tier for r in results)
    resolved = [r for r in results if r.rgid]
    owned = [r for r in resolved if r.owned]
    hard = [a for a, r in zip(albums, results) if not r.rgid]

    lines: list[str] = []
    def p(s: str = "") -> None:
        print(s)
        lines.append(s)

    p("# D0 reconcile spike — results")
    p()
    p(f"Sampled albums: {n}")
    p(f"MusicBrainz live requests this run: {mb_live} (rest served from cache)")
    p()
    p("## Resolution rate (Spotify -> release-group)")
    for tier in ("barcode", "isrc", "text", "none"):
        c = by_tier.get(tier, 0)
        p(f"  {tier:8} {c:4}  {pct(c, n)}")
    p(f"  RESOLVED {len(resolved):4}  {pct(len(resolved), n)}")
    p()
    p("## beets side")
    p(f"  owned albums:               {total_owned}")
    p(f"  carrying mb_releasegroupid: {with_id}  {pct(with_id, total_owned)}  <- accuracy ceiling")
    p()
    p("## Ownership (among resolved albums)")
    p(f"  resolved & owned:     {len(owned)}")
    p(f"  resolved & not-owned: {len(resolved) - len(owned)}")
    p()
    p("## Hard bucket (unresolved) — eyeball for patterns")
    for a in hard:
        p(f"  - {a.artist} — {a.title}  (upc={'y' if a.upc else 'n'} isrcs={len(a.isrcs)})")
    p()
    p("## Sample of resolved matches — hand-verify a subset")
    for a, r in list(zip(albums, results))[:25]:
        if r.rgid:
            p(f"  [{r.tier[:4]:4} {r.confidence:>4}] {'OWNED' if r.owned else '     '} "
              f"{a.artist} — {a.title}  {r.rgid}")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text("\n".join(lines) + "\n")
    (out_dir / "results.json").write_text(json.dumps(
        [{"album": asdict(a), "resolution": asdict(r)} for a, r in zip(albums, results)],
        indent=2))
    p()
    p(f"Wrote {out_dir/'report.md'} and {out_dir/'results.json'}")


def pct(a: int, b: int) -> str:
    return f"({round(100 * a / b) if b else 0}%)"


# ------------------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description="D0 reconcile / identity spike (SPEC §11).")
    ap.add_argument("--client-id", default=os.environ.get("SPOTIFY_CLIENT_ID"))
    ap.add_argument("--client-secret", default=os.environ.get("SPOTIFY_CLIENT_SECRET"))
    ap.add_argument("--redirect", default=os.environ.get(
        "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"))
    ap.add_argument("--sample", type=int, default=80, help="random sample size (0 = all)")
    ap.add_argument("--seed", type=int, default=1, help="sample seed (reproducible)")
    ap.add_argument("--isrc-cap", type=int, default=8, help="max ISRCs queried per album")
    ap.add_argument("--max-isrcs", type=int, default=12, help="max tracks fetched per album")
    ap.add_argument("--text-min-score", type=int, default=90, help="Tier-3 accept threshold")
    ap.add_argument("--beets-cmd", default=os.environ.get("BEETS_CMD"),
                    help="e.g. 'beet' (run beets directly)")
    ap.add_argument("--beets-config", default=os.environ.get("BEETS_CONFIG"))
    ap.add_argument("--owned-file", help="dump of `beet list -a -f '$mb_releasegroupid'`")
    ap.add_argument("--user-agent", default=os.environ.get(
        "MB_USER_AGENT", "mcm-reconcile-spike/0.1 (set MB_USER_AGENT with a contact)"))
    ap.add_argument("--work-dir", default=".spike", help="token + http cache + output")
    args = ap.parse_args()

    if not (args.client_id and args.client_secret):
        raise SystemExit("Set --client-id/--client-secret (or SPOTIFY_CLIENT_ID/SECRET).")

    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    owned, total_owned, with_id = owned_rgids(args.beets_cmd, args.beets_config, args.owned_file)
    print(f"beets: {total_owned} owned albums, {with_id} with a release-group id")

    token = spotify_token(args.client_id, args.client_secret, args.redirect,
                          work / "spotify_token.json")
    print("Fetching saved albums from Spotify...")
    albums = fetch_saved_albums(token, args.max_isrcs)
    print(f"  {len(albums)} saved albums")
    if args.sample and len(albums) > args.sample:
        random.seed(args.seed)
        albums = random.sample(albums, args.sample)
        print(f"  sampled {len(albums)} (seed={args.seed})")

    mb = MB(args.user_agent, work / "mbcache")
    results: list[Resolution] = []
    for i, a in enumerate(albums, 1):
        r = resolve(a, mb, args.isrc_cap, args.text_min_score)
        r.owned = bool(r.rgid and r.rgid in owned)
        results.append(r)
        print(f"  [{i}/{len(albums)}] {r.tier:7} {a.artist} — {a.title}", flush=True)

    report(albums, results, total_owned, with_id, mb.live_requests, work / "out")


if __name__ == "__main__":
    main()
