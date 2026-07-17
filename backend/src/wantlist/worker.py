import logging
import signal
import threading
from collections.abc import Callable
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

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


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    # Jobs run on a thread pool and each also fires immediately at startup (next_run_time=now),
    # so a slow poller (e.g. a cold-start reconcile hammering MusicBrainz) runs concurrently
    # and never blocks the others — the earlier serial startup burst did exactly that.
    scheduler = BackgroundScheduler()
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
    # BackgroundScheduler runs jobs on its own threads; the main thread waits on a stop event
    # with a short poll so a SIGTERM handler (which a long blocking wait would starve) is acted
    # on within ~1s — otherwise `docker stop` SIGKILLs the worker after its grace period (137).
    scheduler = build_scheduler(Settings())
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    scheduler.start()
    try:
        while not stop.wait(1.0):
            pass
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
