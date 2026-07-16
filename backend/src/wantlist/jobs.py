import logging

from .config import Settings
from .db import make_engine, make_session_factory
from .factories import build_ingest_service

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ingest_once()
