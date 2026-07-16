import logging

from .config import Settings
from .db import make_engine, make_session_factory
from .factories import (
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ingest_once()
    reconcile_once()
    poll_plays_once()
