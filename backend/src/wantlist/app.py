from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from . import health
from .adapters.clock import SystemClock
from .adapters.spotify_auth import HttpxSpotifyAuthClient
from .adapters.token_store import TokenStore
from .auth_service import AuthService
from .config import Settings
from .db import make_engine, make_session_factory
from .routers import auth as auth_router


def _build_auth_service(settings: Settings, session_factory: sessionmaker[Session]) -> AuthService:
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)

    app = FastAPI(title="wantlist")
    app.state.settings = settings
    app.state.engine = engine
    app.state.auth_service = _build_auth_service(settings, make_session_factory(engine))
    app.include_router(auth_router.router)

    @app.get("/health")
    def health_endpoint(request: Request) -> JSONResponse:
        cfg: Settings = request.app.state.settings
        postgres = health.check_postgres(request.app.state.engine)
        beets = health.check_beets(cfg.beets_command)
        ok = postgres and beets
        return JSONResponse(
            status_code=200 if ok else 503,
            content={
                "status": "ok" if ok else "degraded",
                "checks": {"postgres": postgres, "beets": beets},
            },
        )

    return app


app = create_app()
