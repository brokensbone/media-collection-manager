from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import health
from .acquire import AcquireService
from .adapters.album_repo import AlbumRepo
from .adapters.clock import SystemClock
from .config import Settings
from .db import make_engine, make_session_factory
from .factories import (
    build_auth_service,
    build_decide_service,
    build_import_runner,
    build_releases_service,
)
from .imports import ImportsService
from .routers import acquire as acquire_router
from .routers import art as art_router
from .routers import auth as auth_router
from .routers import dashboard as dashboard_router
from .routers import decide as decide_router
from .routers import imports as imports_router
from .routers import library as library_router
from .routers import releases as releases_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    app = FastAPI(title="wantlist")
    app.state.settings = settings
    app.state.engine = engine
    app.state.auth_service = build_auth_service(settings, session_factory)
    app.state.album_repo = AlbumRepo(session_factory)
    app.state.decide_service = build_decide_service(settings, session_factory)
    app.state.acquire_service = AcquireService(repo=AlbumRepo(session_factory), clock=SystemClock())
    app.state.releases_service = build_releases_service(settings, session_factory)
    app.state.imports_service = ImportsService(
        repo=AlbumRepo(session_factory),
        runner=build_import_runner(settings, session_factory),
    )
    app.include_router(auth_router.router)
    app.include_router(art_router.router)
    app.include_router(library_router.router)
    app.include_router(decide_router.router)
    app.include_router(acquire_router.router)
    app.include_router(dashboard_router.router)
    app.include_router(releases_router.router)
    app.include_router(imports_router.router)

    @app.get("/health")
    def health_endpoint(request: Request) -> JSONResponse:
        postgres = health.check_postgres(request.app.state.engine)
        beets = health.check_beets()
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
