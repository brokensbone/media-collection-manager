from sqlalchemy.orm import Session, sessionmaker

from .adapters.album_repo import AlbumRepo
from .adapters.art_fetcher import fetch_image
from .adapters.beets import BeetsClient
from .adapters.clock import SystemClock
from .adapters.mb_resolver import HttpxMusicBrainzResolver
from .adapters.spotify_api import HttpxSpotifyApiClient
from .adapters.spotify_auth import HttpxSpotifyAuthClient
from .adapters.token_store import TokenStore
from .artist_watch import ArtistWatchService
from .auth_service import AuthService
from .config import Settings
from .ingest import IngestService
from .play_history import PlayHistoryService
from .reconcile import OwnershipReconciler
from .releases import ReleasesService
from .resolution import ResolutionService


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
        api=HttpxSpotifyApiClient(settings.spotify_api_url, settings.art_target_px),
        repo=AlbumRepo(session_factory),
        tokens=build_auth_service(settings, session_factory),
        fetch_image=fetch_image,
    )


def build_resolution_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> ResolutionService:
    return ResolutionService(
        api=HttpxSpotifyApiClient(settings.spotify_api_url, settings.art_target_px),
        resolver=HttpxMusicBrainzResolver(
            base_url=settings.musicbrainz_url,
            user_agent=settings.musicbrainz_user_agent,
            min_interval=settings.musicbrainz_min_interval,
            text_min_score=settings.musicbrainz_text_min_score,
        ),
        repo=AlbumRepo(session_factory),
        tokens=build_auth_service(settings, session_factory),
    )


def build_ownership_reconciler(
    settings: Settings, session_factory: sessionmaker[Session]
) -> OwnershipReconciler:
    return OwnershipReconciler(
        beets=BeetsClient(settings.beets_config),
        repo=AlbumRepo(session_factory),
    )


def build_play_history_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> PlayHistoryService:
    return PlayHistoryService(
        api=HttpxSpotifyApiClient(settings.spotify_api_url, settings.art_target_px),
        repo=AlbumRepo(session_factory),
        tokens=build_auth_service(settings, session_factory),
    )


def build_artist_watch_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> ArtistWatchService:
    return ArtistWatchService(
        api=HttpxSpotifyApiClient(settings.spotify_api_url, settings.art_target_px),
        repo=AlbumRepo(session_factory),
        tokens=build_auth_service(settings, session_factory),
    )


def build_releases_service(
    settings: Settings, session_factory: sessionmaker[Session]
) -> ReleasesService:
    return ReleasesService(
        api=HttpxSpotifyApiClient(settings.spotify_api_url, settings.art_target_px),
        repo=AlbumRepo(session_factory),
        tokens=build_auth_service(settings, session_factory),
        clock=SystemClock(),
    )
