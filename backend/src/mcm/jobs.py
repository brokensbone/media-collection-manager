import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from .adapters.album_repo import AlbumRepo
from .adapters.beets import BeetsClient
from .adapters.beets_cache import BeetsCatalogCache
from .adapters.mpd import MpdClient, MpdError
from .config import Settings
from .db import make_engine, make_session_factory
from .factories import (
    build_alerts_service,
    build_artist_watch_service,
    build_auth_service,
    build_decide_service,
    build_import_detection_service,
    build_import_runner,
    build_ingest_service,
    build_ownership_reconciler,
    build_play_history_service,
    build_resolution_service,
    build_telegram_worklist_poller,
    build_watchdir_detection_service,
)
from .radio_schedules import RadioScheduleService, ScheduleError

log = logging.getLogger(__name__)


@contextmanager
def heartbeat(session_factory: sessionmaker[Session], job: str) -> Iterator[None]:
    """Record a poller's heartbeat to `job_run` (SPEC §16): success bumps runs + last_success;
    an unexpected error bumps errors + last_error and re-raises so the scheduler still logs it.
    `/metrics` reads these so a stalled or erroring poller can be alerted on."""
    try:
        yield
    except Exception:
        AlbumRepo(session_factory).record_job_error(job, datetime.now(UTC))
        raise
    AlbumRepo(session_factory).record_job_success(job, datetime.now(UTC))


def _session_factory(settings: Settings) -> sessionmaker[Session]:
    return make_session_factory(make_engine(settings.database_url))


def _refresh_library_cache(settings: Settings, session_factory: sessionmaker[Session]) -> None:
    """Snapshot the beets catalogue into the DB (§5) so the API reads it instead of running beet.
    Worker-only: the live `beet list` happens here, never on a page load."""
    beets = BeetsClient()
    BeetsCatalogCache(session_factory).replace(
        beets.all_albums(),
        beets.all_tracks(
            music_directory=settings.music_dir,
            legacy_music_directory=settings.legacy_music_dir,
        ),
    )


def ingest_once(settings: Settings | None = None) -> None:
    """One saves-ingest + art-fetch pass. CLI form: `python -m mcm.jobs`."""
    settings = settings or Settings()
    session_factory = _session_factory(settings)
    with heartbeat(session_factory, "ingest"):
        service = build_ingest_service(settings, session_factory)
        result = service.ingest_saves()
        backfilled = service.backfill_owned_art()  # find covers for owned albums that lack one
        art = service.fetch_missing_art()
        log.info(
            "ingest: added=%s skipped=%s paused=%s art=%s backfilled=%s",
            result.added,
            result.skipped,
            result.paused,
            art,
            backfilled,
        )


def reconcile_once(settings: Settings | None = None) -> None:
    """Resolve unresolved albums, then re-derive ownership against beets (§5)."""
    settings = settings or Settings()
    session_factory = _session_factory(settings)
    with heartbeat(session_factory, "reconcile"):
        resolution = build_resolution_service(settings, session_factory).resolve_unresolved()
        reconciled = build_ownership_reconciler(settings, session_factory).reconcile()
        build_alerts_service(settings, session_factory).owned(reconciled.newly_owned)
        _refresh_library_cache(settings, session_factory)  # keep the API's catalogue cache current
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
    session_factory = _session_factory(settings)
    with heartbeat(session_factory, "play_history"):
        result = build_play_history_service(settings, session_factory).poll()
        log.info("play-history: added=%s paused=%s", result.added, result.paused)


def watch_artists_once(settings: Settings | None = None) -> None:
    """One artist-watch pass — surface new releases as suggested (§6b)."""
    settings = settings or Settings()
    session_factory = _session_factory(settings)
    with heartbeat(session_factory, "artist_watch"):
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
    session_factory = _session_factory(settings)
    with heartbeat(session_factory, "transmission"):
        result = build_import_detection_service(settings, session_factory).poll()
        log.info("transmission: detected=%s", result.detected)


def run_imports_once(settings: Settings | None = None) -> None:
    """Process queued imports in the background (§12/§13), so the operator can tick a batch
    on the Import screen and come back — each moves to imported/failed on its own."""
    settings = settings or Settings()
    session_factory = _session_factory(settings)
    with heartbeat(session_factory, "imports"):
        processed = build_import_runner(settings, session_factory).run_queued()
        if processed:
            # An import may have changed the library.
            _refresh_library_cache(settings, session_factory)
            log.info("imports: processed=%s", processed)


def poll_watchdir_once(settings: Settings | None = None) -> None:
    """One watch-dir scan — detect settled drops and match them to wants (§13). Disabled when
    no watch path is configured."""
    settings = settings or Settings()
    if not settings.watchdir_path:
        return
    session_factory = _session_factory(settings)
    with heartbeat(session_factory, "watchdir"):
        result = build_watchdir_detection_service(settings, session_factory).poll()
        log.info("watchdir: detected=%s", result.detected)


def alerts_once(settings: Settings | None = None) -> None:
    """Fire operator alerts for re-auth-due and a triage backlog (§8d)."""
    settings = settings or Settings()
    session_factory = _session_factory(settings)
    with heartbeat(session_factory, "alerts"):
        reauth_due = build_auth_service(settings, session_factory).status().reauth_due
        decide_count = len(build_decide_service(settings, session_factory).queue())
        build_alerts_service(settings, session_factory).check(
            reauth_due=reauth_due, decide_count=decide_count
        )
        log.info("alerts: reauth_due=%s decide_count=%s", reauth_due, decide_count)


def poll_telegram_worklist_once(settings: Settings | None = None) -> None:
    """Receive explicit /work commands and inline-button callbacks; no proactive messages."""
    settings = settings or Settings()
    session_factory = _session_factory(settings)
    poller = build_telegram_worklist_poller(settings, session_factory)
    if poller is None:
        return
    with heartbeat(session_factory, "telegram_worklist"):
        poller.poll()


def _radio_paths(settings: Settings, session_factory: sessionmaker[Session]) -> list[str] | None:
    today = datetime.now(ZoneInfo(settings.radio_timezone)).date()
    return RadioScheduleService(session_factory).playable_paths(today)


def load_radio_once(settings: Settings | None = None) -> None:
    """At 07:00 local time, replace MPD's queue with today's complete plan, paused."""
    settings = settings or Settings()
    if not settings.mpd_host:
        log.info("radio load skipped: MCM_MPD_HOST is not configured")
        return
    session_factory = _session_factory(settings)
    with heartbeat(session_factory, "radio_load"):
        try:
            paths = _radio_paths(settings, session_factory)
            if paths is None:
                log.info("radio load skipped: no schedule for today")
                return
            mpd = MpdClient(settings.mpd_host, settings.mpd_port)
            mpd.refresh_database()
            mpd.load(paths)
        except (MpdError, ScheduleError):
            log.exception("radio load failed")
            raise
        log.info("radio loaded: tracks=%s", len(paths))


def play_radio_once(settings: Settings | None = None) -> None:
    """At 09:00 local time, start only the queue that this morning's plan resolved to."""
    settings = settings or Settings()
    if not settings.mpd_host:
        log.info("radio play skipped: MCM_MPD_HOST is not configured")
        return
    session_factory = _session_factory(settings)
    with heartbeat(session_factory, "radio_play"):
        try:
            paths = _radio_paths(settings, session_factory)
            if paths is None:
                log.info("radio play skipped: no schedule for today")
                return
            mpd = MpdClient(settings.mpd_host, settings.mpd_port)
            if mpd.playlist_paths() != paths:
                log.warning("radio play skipped: MPD queue no longer matches today's schedule")
                return
            mpd.play()
        except (MpdError, ScheduleError):
            log.exception("radio play failed")
            raise
        log.info("radio playing: tracks=%s", len(paths))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ingest_once()
    reconcile_once()
    poll_plays_once()
    watch_artists_once()
    poll_transmission_once()
    poll_watchdir_once()
    run_imports_once()
    alerts_once()
