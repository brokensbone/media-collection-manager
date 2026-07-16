import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

from wantlist.db import make_session_factory
from wantlist.models import Base

# testcontainers' ryuk reaper bind-mounts the docker socket, which colima rejects; our
# containers are context-managed (`with ...`), so the reaper is just a safety net.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


@pytest.fixture(scope="session")
def pg_session_factory() -> Iterator[sessionmaker[Session]]:
    """A session factory backed by a real Postgres (schema via metadata.create_all)."""
    with PostgresContainer("postgres:16", driver="psycopg") as pg:
        engine = create_engine(pg.get_connection_url())
        Base.metadata.create_all(engine)
        yield make_session_factory(engine)
        engine.dispose()
