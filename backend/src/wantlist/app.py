from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="wantlist")

    @app.get("/health")
    def health() -> dict[str, str]:
        # D2 extends this to verify Postgres + beets reachability.
        return {"status": "ok"}

    return app


app = create_app()
