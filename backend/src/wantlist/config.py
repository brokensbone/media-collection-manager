from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """The environment contract (SPEC §8a). All from env (WANTLIST_*) or a .env file."""

    model_config = SettingsConfigDict(env_prefix="WANTLIST_", env_file=".env", extra="ignore")

    # Storage
    database_url: str = "postgresql+psycopg://localhost:5432/wantlist"

    # beets seam (§5): beets is bundled; this points at the beets config, whose
    # `library:`/`directory:` reference the mounted library.db + music.
    beets_config: str | None = None

    # Spotify (§8c). Base URLs are overridable so E2E can point at a stub (§14).
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8000/auth/spotify/callback"
    spotify_scopes: str = "user-library-read user-library-modify"  # modify: Save/Want (§6b)
    spotify_accounts_url: str = "https://accounts.spotify.com"
    spotify_api_url: str = "https://api.spotify.com/v1"

    # Re-auth countdown (§8c): refresh tokens expire ~6 months after authorization.
    reauth_lifetime_days: int = 183
    reauth_warn_days: int = 21

    # Where to send the browser after a successful callback.
    frontend_url: str = "/"

    # Ingest (§4/§4b): poll interval and the cover-art size to keep.
    saves_poll_seconds: int = 3600
    art_target_px: int = 300

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

    # MusicBrainz resolution (§5, §11). Base URL overridable for tests/E2E (§14).
    musicbrainz_url: str = "https://musicbrainz.org/ws/2"
    musicbrainz_user_agent: str = "wantlist/0.1 ( https://github.com/EdwardSalkeld )"
    musicbrainz_min_interval: float = 1.1  # MB asks for <= 1 req/sec
    musicbrainz_text_min_score: int = 90  # Tier-3 fuzzy accept threshold
