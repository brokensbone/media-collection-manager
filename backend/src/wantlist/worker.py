import logging
from collections.abc import Callable
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from .config import Settings
from .jobs import (
    alerts_once,
    ingest_once,
    poll_plays_once,
    poll_transmission_once,
    poll_watchdir_once,
    reconcile_once,
    run_imports_once,
    watch_artists_once,
)

log = logging.getLogger(__name__)


def build_scheduler(settings: Settings) -> BlockingScheduler:
    # Jobs run on a thread pool and each also fires immediately at startup (next_run_time=now),
    # so a slow poller (e.g. a cold-start reconcile hammering MusicBrainz) runs concurrently
    # and never blocks the others — the earlier serial startup burst did exactly that.
    scheduler = BlockingScheduler()
    now = datetime.now()

    def every(job: Callable[[Settings], None], seconds: int, job_id: str) -> None:
        scheduler.add_job(
            job, "interval", seconds=seconds, args=[settings], id=job_id, next_run_time=now
        )

    every(ingest_once, settings.saves_poll_seconds, "ingest_saves")
    every(reconcile_once, settings.saves_poll_seconds, "reconcile")
    every(poll_plays_once, settings.recently_played_poll_seconds, "play_history")
    every(watch_artists_once, settings.artist_watch_poll_seconds, "artist_watch")
    if settings.transmission_rpc_url:
        every(poll_transmission_once, settings.transmission_poll_seconds, "transmission")
    if settings.watchdir_path:
        every(poll_watchdir_once, settings.watchdir_poll_seconds, "watchdir")
    every(run_imports_once, settings.import_process_seconds, "imports")
    every(alerts_once, settings.alerts_poll_seconds, "alerts")
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # Each job fires immediately (and then on its interval) on the scheduler's thread pool,
    # so startup runs happen concurrently and a slow/failing one can't block the rest.
    build_scheduler(Settings()).start()


if __name__ == "__main__":
    main()
