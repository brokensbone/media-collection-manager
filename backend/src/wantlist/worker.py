import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from .config import Settings
from .jobs import ingest_once, poll_plays_once, reconcile_once, watch_artists_once

log = logging.getLogger(__name__)


def build_scheduler(settings: Settings) -> BlockingScheduler:
    scheduler = BlockingScheduler()
    scheduler.add_job(
        ingest_once,
        "interval",
        seconds=settings.saves_poll_seconds,
        args=[settings],
        id="ingest_saves",
    )
    scheduler.add_job(
        reconcile_once,
        "interval",
        seconds=settings.saves_poll_seconds,
        args=[settings],
        id="reconcile",
    )
    scheduler.add_job(
        poll_plays_once,
        "interval",
        seconds=settings.recently_played_poll_seconds,
        args=[settings],
        id="play_history",
    )
    scheduler.add_job(
        watch_artists_once,
        "interval",
        seconds=settings.artist_watch_poll_seconds,
        args=[settings],
        id="artist_watch",
    )
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    ingest_once(settings)  # run once at startup, then on the intervals
    reconcile_once(settings)
    poll_plays_once(settings)
    watch_artists_once(settings)
    build_scheduler(settings).start()


if __name__ == "__main__":
    main()
