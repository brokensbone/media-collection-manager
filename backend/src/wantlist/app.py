from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import health
from .adapters.album_repo import AlbumRepo
from .config import Settings
from .db import make_engine, make_session_factory
from .factories import (
    build_acquire_service,
    build_auth_service,
    build_decide_service,
    build_releases_service,
    build_transmission_service,
)
from .imports import ImportsService
from .metrics import MetricsService
from .routers import acquire as acquire_router
from .routers import art as art_router
from .routers import auth as auth_router
from .routers import dashboard as dashboard_router
from .routers import decide as decide_router
from .routers import imports as imports_router
from .routers import library as library_router
from .routers import metrics as metrics_router
from .routers import releases as releases_router
from .routers import transmission as transmission_router


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
    app.state.acquire_service = build_acquire_service(settings, session_factory)
    app.state.releases_service = build_releases_service(settings, session_factory)
    app.state.imports_service = ImportsService(repo=AlbumRepo(session_factory))
    app.state.transmission_service = build_transmission_service(settings, session_factory)
    app.state.metrics_service = MetricsService(
        repo=AlbumRepo(session_factory),
        auth=build_auth_service(settings, session_factory),
    )
    app.include_router(auth_router.router)
    app.include_router(art_router.router)
    app.include_router(library_router.router)
    app.include_router(decide_router.router)
    app.include_router(acquire_router.router)
    app.include_router(dashboard_router.router)
    app.include_router(releases_router.router)
    app.include_router(imports_router.router)
    app.include_router(transmission_router.router)
    app.include_router(metrics_router.router)

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

    # Serve the built SPA last so it only catches paths the API routers didn't (D10). All
    # frontend calls are same-origin relative paths, so this needs no proxy.
    if settings.static_dir:
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="spa")

    return app


app = create_app()
