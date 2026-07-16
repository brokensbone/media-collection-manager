from sqlalchemy.orm import Session, sessionmaker

from .adapters.album_repo import AlbumRepo
from .adapters.art_fetcher import fetch_image
from .adapters.clock import SystemClock
from .adapters.spotify_api import HttpxSpotifyApiClient
from .adapters.spotify_auth import HttpxSpotifyAuthClient
from .adapters.token_store import TokenStore
from .auth_service import AuthService
from .config import Settings
from .ingest import IngestService


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
