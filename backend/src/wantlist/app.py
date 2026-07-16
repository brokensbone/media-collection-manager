from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import health
from .config import Settings
from .db import make_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="wantlist")
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)

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
