from sqlalchemy.orm import Session, sessionmaker

from .acquire import AcquireService
from .adapters.album_repo import AlbumRepo
from .adapters.art_fetcher import fetch_image
from .adapters.beets import BeetsClient
from .adapters.beets_cache import BeetsCatalogCache
from .adapters.clock import SystemClock
from .adapters.event_log import WorkerEventLog
from .adapters.mb_resolver import HttpxMusicBrainzResolver
from .adapters.notifier import WebhookNotifier
from .adapters.rsync import RsyncTransfer
from .adapters.spotify_api import HttpxSpotifyApiClient
from .adapters.spotify_auth import HttpxSpotifyAuthClient
from .adapters.tags import MediaFileTagReader
from .adapters.token_store import TokenStore
from .adapters.transmission import HttpxTransmissionClient
from .alerts import AlertsService
from .artist_watch import ArtistWatchService
from .auth_service import AuthService
from .config import Settings
from .decide import DecideService
from .imports import (
    ImportDetectionService,
    ImportRunner,
    TransmissionStager,
    VideoLibraryImporter,
    WatchdirDetectionService,
    WatchdirStager,
)
from .ingest import IngestService
from .library_assist import LibraryAssistService
from .models import ImportSource
from .play_history import PlayHistoryService
from .reconcile import OwnershipReconciler
from .releases import ReleasesService
from .resolution import ResolutionService
from .reverse_match import ReverseMatcher
from .transmission_service import TransmissionService


def build_auth_service(settings: Settings, session_factory: sessionmaker[Session]) -> AuthService:
    client = HttpxSpotifyAuthClient(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        redirect_uri=settings.spotify_redirect_uri,
        scopes=settings.spotify_scopes,
        accounts_url=settings.spotify_accounts_url,
    )
    return AuthService(
        client=client,
        store=TokenStore(session_factory),
        clock=SystemClock(),
        scopes=settings.spotify_scopes,
        lifetime_days=settings.reauth_lifetime_days,
        warn_days=settings.reauth_warn_days,
    )


def build_ingest_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> IngestService:
    return IngestService(
        api=HttpxSpotifyApiClient(
            settings.spotify_api_url, settings.art_target_px, settings.spotify_market
        ),
        repo=AlbumRepo(session_factory),
        tokens=build_auth_service(settings, session_factory),
        fetch_image=fetch_image,
        events=WorkerEventLog(session_factory),
    )


def build_resolution_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> ResolutionService:
    return ResolutionService(
        api=HttpxSpotifyApiClient(
            settings.spotify_api_url, settings.art_target_px, settings.spotify_market
        ),
        resolver=HttpxMusicBrainzResolver(
            base_url=settings.musicbrainz_url,
            user_agent=settings.musicbrainz_user_agent,
            min_interval=settings.musicbrainz_min_interval,
            text_min_score=settings.musicbrainz_text_min_score,
        ),
        repo=AlbumRepo(session_factory),
        tokens=build_auth_service(settings, session_factory),
        max_per_run=settings.resolution_max_per_run,
        events=WorkerEventLog(session_factory),
    )


def build_ownership_reconciler(
    settings: Settings, session_factory: sessionmaker[Session]
) -> OwnershipReconciler:
    return OwnershipReconciler(
        beets=BeetsClient(),
        repo=AlbumRepo(session_factory),
        events=WorkerEventLog(session_factory),
    )


def build_play_history_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> PlayHistoryService:
    return PlayHistoryService(
        api=HttpxSpotifyApiClient(
            settings.spotify_api_url, settings.art_target_px, settings.spotify_market
        ),
        repo=AlbumRepo(session_factory),
        tokens=build_auth_service(settings, session_factory),
    )


def build_artist_watch_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> ArtistWatchService:
    return ArtistWatchService(
        api=HttpxSpotifyApiClient(
            settings.spotify_api_url, settings.art_target_px, settings.spotify_market
        ),
        repo=AlbumRepo(session_factory),
        tokens=build_auth_service(settings, session_factory),
        events=WorkerEventLog(session_factory),
    )


def build_decide_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> DecideService:
    return DecideService(
        repo=AlbumRepo(session_factory),
        clock=SystemClock(),
        forgotten_days=settings.verdict_forgotten_days,
        snooze_days=settings.verdict_snooze_days,
        listened_tracks=settings.verdict_listened_tracks,
        listened_days=settings.verdict_listened_days,
    )


def build_alerts_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> AlertsService:
    return AlertsService(
        notifier=WebhookNotifier(settings.notification_webhook_url),
        repo=AlbumRepo(session_factory),
        triage_threshold=settings.notify_triage_threshold,
    )


def build_import_detection_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> ImportDetectionService:
    return ImportDetectionService(
        transmission=HttpxTransmissionClient(
            rpc_url=settings.transmission_rpc_url,
            user=settings.transmission_user,
            password=settings.transmission_password,
        ),
        repo=AlbumRepo(session_factory),
        match_threshold=settings.import_match_threshold,
        jellyfin_tv_root=settings.jellyfin_tv_root,
        jellyfin_film_root=settings.jellyfin_film_root,
        events=WorkerEventLog(session_factory),
    )


def build_transmission_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> TransmissionService:
    return TransmissionService(
        repo=AlbumRepo(session_factory),
        client=HttpxTransmissionClient(
            rpc_url=settings.transmission_rpc_url,
            user=settings.transmission_user,
            password=settings.transmission_password,
        ),
        transfer=RsyncTransfer(
            host=settings.transmission_ssh_host,
            port=settings.transmission_ssh_port,
            user=settings.transmission_ssh_user,
            ssh_key=settings.transmission_ssh_key,
        ),
        api_configured=bool(settings.transmission_rpc_url),
        ssh_configured=bool(settings.transmission_ssh_host),
    )


def build_watchdir_detection_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> WatchdirDetectionService:
    return WatchdirDetectionService(
        repo=AlbumRepo(session_factory),
        tags=MediaFileTagReader(),
        clock=SystemClock(),
        watch_dir=settings.watchdir_path,
        archive_subdir=settings.watchdir_archive_subdir,
        settle_seconds=settings.watchdir_settle_seconds,
        match_threshold=settings.import_match_threshold,
        events=WorkerEventLog(session_factory),
    )


def build_import_runner(settings: Settings, session_factory: sessionmaker[Session]) -> ImportRunner:
    transmission = TransmissionStager(
        RsyncTransfer(
            host=settings.transmission_ssh_host,
            port=settings.transmission_ssh_port,
            user=settings.transmission_ssh_user,
            ssh_key=settings.transmission_ssh_key,
        )
    )
    watchdir = WatchdirStager(
        watch_dir=settings.watchdir_path,
        disposition=settings.watchdir_disposition,
        archive_subdir=settings.watchdir_archive_subdir,
    )
    beets = BeetsClient()
    reverse_matcher = ReverseMatcher(
        repo=AlbumRepo(session_factory),
        api=HttpxSpotifyApiClient(
            settings.spotify_api_url, settings.art_target_px, settings.spotify_market
        ),
        tokens=build_auth_service(settings, session_factory),
    )
    return ImportRunner(
        repo=AlbumRepo(session_factory),
        stagers={
            ImportSource.transmission: transmission,
            ImportSource.watchdir: watchdir,
        },
        beets=beets,
        video=VideoLibraryImporter(),
        inbox=settings.import_inbox_path,
        catalog=beets,
        reverse_matcher=reverse_matcher,
        events=WorkerEventLog(session_factory),
    )


def build_library_assist_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> LibraryAssistService:
    # Reads the DB-cached catalogue, never live beets — this service is API-facing (Owned view,
    # Acquire), and the API must never shell out to `beet` (§5). The worker keeps the cache fresh.
    return LibraryAssistService(
        repo=AlbumRepo(session_factory),
        catalog=BeetsCatalogCache(session_factory),
    )


def build_acquire_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> AcquireService:
    return AcquireService(
        repo=AlbumRepo(session_factory),
        assist=build_library_assist_service(settings, session_factory),
    )


def build_releases_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> ReleasesService:
    return ReleasesService(
        api=HttpxSpotifyApiClient(
            settings.spotify_api_url, settings.art_target_px, settings.spotify_market
        ),
        repo=AlbumRepo(session_factory),
        tokens=build_auth_service(settings, session_factory),
        clock=SystemClock(),
    )
