"""Verify the durable audit schema against PostgreSQL's actual migration path."""

import logging

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from testcontainers.postgres import PostgresContainer

from mcm.models import Base


def test_autofile_migration_round_trip(monkeypatch):
    with PostgresContainer("postgres:16", driver="psycopg") as pg:
        monkeypatch.setenv("MCM_DATABASE_URL", pg.get_connection_url())
        application_log = logging.getLogger("mcm.adapters.beets")
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(pg.get_connection_url())
        try:
            with engine.connect() as connection:
                # Limit comparison to this migration; older tables have unrelated schema drift.
                context = MigrationContext.configure(
                    connection,
                    opts={
                        "include_object": lambda obj, name, kind, reflected, compared: (
                            kind != "table" or name == "autofile_run"
                        ),
                    },
                )
                assert compare_metadata(context, Base.metadata) == []
                assert "autofile_run" in inspect(connection).get_table_names()
            command.downgrade(config, "b8c9d0e1f2a3")
            assert "autofile_run" not in inspect(engine).get_table_names()
            command.upgrade(config, "head")
            assert "autofile_run" in inspect(engine).get_table_names()
            assert not application_log.disabled
        finally:
            engine.dispose()
