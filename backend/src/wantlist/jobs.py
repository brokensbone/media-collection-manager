import logging

from .config import Settings
from .db import make_engine, make_session_factory
from .factories import (
    build_alerts_service,
    build_artist_watch_service,
    build_auth_service,
    build_decide_service,
    build_import_detection_service,
    build_ingest_service,
    build_ownership_reconciler,
    build_play_history_service,
    build_resolution_service,
)

log = logging.getLogger(__name__)


def ingest_once(settings: Settings | None = None) -> None:
    """One saves-ingest + art-fetch pass. CLI form: `python -m wantlist.jobs`."""
    settings = settings or Settings()
    session_factory = make_session_factory(make_engine(settings.database_url))
    service = build_ingest_service(settings, session_factory)
    result = service.ingest_saves()
    art = service.fetch_missing_art()
    log.info(
        "ingest: added=%s skipped=%s paused=%s art=%s",
        result.added,
        result.skipped,
        result.paused,
        art,
    )


def reconcile_once(settings: Settings | None = None) -> None:
    """Resolve unresolved albums, then re-derive ownership against beets (§5)."""
    settings = settings or Settings()
    session_factory = make_session_factory(make_engine(settings.database_url))
    resolution = build_resolution_service(settings, session_factory).resolve_unresolved()
    reconciled = build_ownership_reconciler(settings, session_factory).reconcile()
    build_alerts_service(settings, session_factory).owned(reconciled.newly_owned)
    log.info(
        "reconcile: resolved=%s unresolved=%s paused=%s newly_owned=%s",
        resolution.resolved,
        resolution.unresolved,
        resolution.paused,
        reconciled.newly_owned,
    )


def poll_plays_once(settings: Settings | None = None) -> None:
    """One recently-played poll into the play-history log (§4a)."""
    settings = settings or Settings()
    session_factory = make_session_factory(make_engine(settings.database_url))
    result = build_play_history_service(settings, session_factory).poll()
    log.info("play-history: added=%s paused=%s", result.added, result.paused)


def watch_artists_once(settings: Settings | None = None) -> None:
    """One artist-watch pass — surface new releases as suggested (§6b)."""
    settings = settings or Settings()
    session_factory = make_session_factory(make_engine(settings.database_url))
    result = build_artist_watch_service(settings, session_factory).poll()
    log.info(
        "artist-watch: artists=%s added=%s paused=%s",
        result.artists,
        result.added,
        result.paused,
    )


def poll_transmission_once(settings: Settings | None = None) -> None:
    """One Transmission poll — detect completed downloads and match them to wants (§12).
    Disabled when no rpc url is configured."""
    settings = settings or Settings()
    if not settings.transmission_rpc_url:
        return
    session_factory = make_session_factory(make_engine(settings.database_url))
    result = build_import_detection_service(settings, session_factory).poll()
    log.info("transmission: detected=%s", result.detected)


def alerts_once(settings: Settings | None = None) -> None:
    """Fire operator alerts for re-auth-due and a triage backlog (§8d)."""
    settings = settings or Settings()
    session_factory = make_session_factory(make_engine(settings.database_url))
    reauth_due = build_auth_service(settings, session_factory).status().reauth_due
    decide_count = len(build_decide_service(settings, session_factory).queue())
    build_alerts_service(settings, session_factory).check(
        reauth_due=reauth_due, decide_count=decide_count
    )
    log.info("alerts: reauth_due=%s decide_count=%s", reauth_due, decide_count)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ingest_once()
    reconcile_once()
    poll_plays_once()
    watch_artists_once()
    poll_transmission_once()
    alerts_once()
