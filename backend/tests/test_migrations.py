"""Integration test (SPEC §14): migrations apply cleanly on a fresh Postgres, and the
real /health check passes against it. Requires Docker (testcontainers)."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from testcontainers.postgres import PostgresContainer

from mcm.app import create_app
from mcm.config import Settings

EXPECTED_TABLES = {
    "album",
    "play_history",
    "album_art",
    "spotify_auth",
    "box",
    "record_box",
    "alembic_version",
}


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver="psycopg") as pg:
        url = pg.get_connection_url()
        monkey = pytest.MonkeyPatch()
        monkey.setenv("MCM_DATABASE_URL", url)  # env.py builds its url from Settings
        command.upgrade(Config("alembic.ini"), "head")
        monkey.undo()
        yield url


def test_migrations_create_all_tables(pg_url: str) -> None:
    engine = create_engine(pg_url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert EXPECTED_TABLES <= tables


def test_migration_seeds_the_root_collection(pg_url: str) -> None:
    engine = create_engine(pg_url)
    with engine.connect() as conn:
        roots = conn.execute(text("SELECT name FROM box WHERE parent_id IS NULL")).fetchall()
    engine.dispose()
    assert [r[0] for r in roots] == ["Collection"]  # exactly one seeded root


def test_health_ok_against_real_postgres(pg_url: str) -> None:
    client = TestClient(create_app(Settings(database_url=pg_url)))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["checks"]["postgres"] is True
