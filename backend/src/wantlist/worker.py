import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from .config import Settings
from .jobs import (
    alerts_once,
    ingest_once,
    poll_plays_once,
    poll_transmission_once,
    poll_watchdir_once,
    reconcile_once,
    watch_artists_once,
)

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
    if settings.transmission_rpc_url:
        scheduler.add_job(
            poll_transmission_once,
            "interval",
            seconds=settings.transmission_poll_seconds,
            args=[settings],
            id="transmission",
        )
    if settings.watchdir_path:
        scheduler.add_job(
            poll_watchdir_once,
            "interval",
            seconds=settings.watchdir_poll_seconds,
            args=[settings],
            id="watchdir",
        )
    scheduler.add_job(
        alerts_once,
        "interval",
        seconds=settings.alerts_poll_seconds,
        args=[settings],
        id="alerts",
    )
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    # Run each job once at startup, then on the intervals. Guard each: a transient failure
    # (e.g. a MusicBrainz 503 during reconcile) must not stop the scheduler from starting —
    # otherwise one flaky upstream call kills every poller. The scheduled run retries later.
    for job in (
        ingest_once,
        reconcile_once,
        poll_plays_once,
        watch_artists_once,
        poll_transmission_once,
        poll_watchdir_once,
        alerts_once,
    ):
        try:
            job(settings)
        except Exception:
            log.exception("startup run of %s failed; continuing", job.__name__)
    build_scheduler(settings).start()


if __name__ == "__main__":
    main()
