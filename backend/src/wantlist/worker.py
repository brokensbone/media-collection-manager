import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from .config import Settings
from .jobs import ingest_once

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
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    ingest_once(settings)  # run once at startup, then on the interval
    build_scheduler(settings).start()


if __name__ == "__main__":
    main()
