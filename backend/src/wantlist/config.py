from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """The environment contract (SPEC §8a). All from env (WANTLIST_*) or a .env file."""

    model_config = SettingsConfigDict(env_prefix="WANTLIST_", env_file=".env", extra="ignore")

    # Storage
    database_url: str = "postgresql+psycopg://localhost:5432/wantlist"

    # Optional: serve the built frontend (SPA) from this directory at `/`, so a single
    # container can serve both UI and API on one origin (D10). Empty = API only (dev uses Vite).
    static_dir: str = ""

    # beets seam (§5): beets is bundled and reads `BEETSDIR` from the environment (set by the
    # deploy to the mounted beets directory) for its config + library. No app setting needed.

    # Spotify (§8c). Base URLs are overridable so E2E can point at a stub (§14).
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8000/auth/spotify/callback"
    spotify_scopes: str = "user-library-read user-library-modify"  # modify: Save/Want (§6b)
    spotify_accounts_url: str = "https://accounts.spotify.com"
    spotify_api_url: str = "https://api.spotify.com/v1"
    # Country for artist-album lookups (§6b). Without it Spotify returns per-market duplicate
    # album ids, so an old release resurfaces as "new"; it also filters to what you can play.
    spotify_market: str = "GB"

    # Re-auth countdown (§8c): refresh tokens expire ~6 months after authorization.
    reauth_lifetime_days: int = 183
    reauth_warn_days: int = 21

    # Where to send the browser after a successful callback.
    frontend_url: str = "/"

    # Ingest (§4/§4b): poll interval and the cover-art size to keep.
    saves_poll_seconds: int = 3600
    art_target_px: int = 300

    # Crates (§2): soft cap on a box's loose (direct) record count — a UI nudge to split, never
    # a hard gate. Tunable.
    crate_soft_cap: int = 50

    # Verdict / Decide (§6a): the "forgotten" (time) and "listened" (play-history) triggers.
    verdict_forgotten_days: int = 21
    verdict_snooze_days: int = 14
    verdict_listened_tracks: int = 4
    verdict_listened_days: int = 3

    # Play-history polling (§4a).
    recently_played_poll_seconds: int = 1800

    # Artist-watch / new releases (§6b).
    artist_watch_poll_seconds: int = 86400

    # Notifications (§8d, D13). Empty webhook = disabled; Slack-compatible {"text": ...}.
    notification_webhook_url: str = ""
    notify_triage_threshold: int = 10
    alerts_poll_seconds: int = 3600

    # Transmission auto-land (§12, D14). Empty rpc url = disabled. Files are pulled off the
    # seedbox with rsync-over-SSH into the local inbox; imports COPY (never move) so seeding
    # is safe. RPC (control/metadata) and SSH (file bytes) are two distinct credentials.
    transmission_rpc_url: str = ""
    transmission_user: str = ""
    transmission_password: str = ""
    transmission_ssh_host: str = ""
    transmission_ssh_port: int = 22
    transmission_ssh_user: str = ""
    transmission_ssh_key: str = ""  # path to the private key rsync's ssh should use
    # Max seconds for a single torrent's rsync off the seedbox. Generous by default: a multi-GB
    # film over a slow seedbox link can take hours, and the old 30-min cap failed them outright.
    # Imports run one at a time, so a very large transfer does hold up the queue behind it.
    transmission_transfer_timeout_seconds: int = 21600  # 6 hours
    import_inbox_path: str = "/inbox"
    # The Tasks view shows completed imports (imported/skipped) from this many days back; older
    # completed imports live in the archive (reached from Tasks), not the default task list.
    import_completed_window_days: int = 3
    transmission_poll_seconds: int = 3600
    import_match_threshold: float = 0.5
    import_process_seconds: int = 30  # how often the worker imports queued acquisitions
    tv_root: str = ""
    film_root: str = ""

    # Watch-dir import (§13, D15). Empty path = disabled. Bandcamp zips / dropped folders are
    # scanned, matched by embedded tags, and one-click imported; the drop is ours, so it's
    # disposed after import (archive default / delete / leave).
    watchdir_path: str = ""
    watchdir_poll_seconds: int = 300
    watchdir_settle_seconds: int = 60  # skip drops modified more recently (still copying)
    watchdir_disposition: str = "archive"  # archive | delete | leave
    watchdir_archive_subdir: str = "done"

    # MusicBrainz resolution (§5, §11). Base URL overridable for tests/E2E (§14).
    musicbrainz_url: str = "https://musicbrainz.org/ws/2"
    musicbrainz_user_agent: str = "wantlist/0.1 ( https://github.com/EdwardSalkeld )"
    musicbrainz_min_interval: float = 2.0  # MB asks for <= 1 req/sec; stay well under it (~0.5/s)
    musicbrainz_text_min_score: int = 90  # Tier-3 fuzzy accept threshold
    resolution_max_per_run: int = 100  # cap MB lookups per reconcile (cold-start politeness)
    # Exponential backoff for the MB-absent tail (§11): after each "no match" an album waits
    # base * 2**attempts (capped) before it's re-checked, so a release MB simply doesn't have
    # isn't re-queried every hourly reconcile forever — it decays from hourly to ~weekly.
    resolution_backoff_base_seconds: int = 3600  # first retry ~1h after a miss
    resolution_backoff_cap_seconds: int = 604800  # never wait more than ~1 week
    # Abort a resolution pass after this many consecutive "couldn't reach MusicBrainz" errors:
    # MB is down/throttling, so stop hammering it (and the log) and retry next reconcile.
    resolution_error_circuit_break: int = 8
