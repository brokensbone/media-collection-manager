from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mcm.adapters.album_repo import AlbumRepo
from mcm.app import create_app
from mcm.config import Settings
from mcm.domain.auth import AuthStatus
from mcm.jobs import heartbeat
from mcm.metrics import MetricsService
from mcm.models import Album, AlbumState, Provenance

T1 = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


class StubAuth:
    def __init__(self, status: AuthStatus) -> None:
        self._status = status

    def status(self) -> AuthStatus:
        return self._status


def _connected(days: int) -> StubAuth:
    return StubAuth(
        AuthStatus(connected=True, authorized_at=T1, reauth_in_days=days, reauth_due=False)
    )


def _add(sf: sessionmaker[Session], *, title: str, state: AlbumState) -> None:
    with sf() as session:
        session.add(
            Album(
                spotify_id=title,
                artist="A",
                title=title,
                state=state,
                provenance=Provenance.spotify_save,
            )
        )
        session.commit()


# --- heartbeat repo + context ---------------------------------------------------------


def test_record_job_success_upserts_and_increments(
    clean_album_tables: sessionmaker[Session],
) -> None:
    repo = AlbumRepo(clean_album_tables)
    repo.record_job_success("ingest", T1)
    repo.record_job_success("ingest", T1)

    (row,) = repo.job_runs()
    assert (row.job, row.runs, row.errors) == ("ingest", 2, 0)
    assert row.last_success_at is not None


def test_heartbeat_records_success_and_error(
    clean_album_tables: sessionmaker[Session],
) -> None:
    sf = clean_album_tables
    with heartbeat(sf, "reconcile"):
        pass  # a clean run
    with pytest.raises(RuntimeError), heartbeat(sf, "reconcile"):
        raise RuntimeError("boom")  # an errored run is recorded and re-raised

    (row,) = AlbumRepo(sf).job_runs()
    assert row.runs == 1
    assert row.errors == 1


# --- metrics rendering ----------------------------------------------------------------


def test_render_exposes_the_key_series(clean_album_tables: sessionmaker[Session]) -> None:
    sf = clean_album_tables
    _add(sf, title="w1", state=AlbumState.wanted)
    _add(sf, title="w2", state=AlbumState.wanted)
    _add(sf, title="o1", state=AlbumState.owned)
    repo = AlbumRepo(sf)
    repo.record_job_success("ingest", T1)

    text = MetricsService(repo=repo, auth=_connected(42)).render()  # type: ignore[arg-type]

    assert "mcm_spotify_connected 1" in text
    assert "mcm_spotify_reauth_days_remaining 42" in text
    assert 'mcm_albums{state="wanted"} 2' in text
    assert 'mcm_albums{state="owned"} 1' in text
    assert 'mcm_albums{state="saved"} 0' in text  # absent states still emitted
    assert "mcm_albums_missing_art 0" in text
    assert f'mcm_job_last_success_timestamp{{job="ingest"}} {int(T1.timestamp())}' in text
    assert 'mcm_job_runs_total{job="ingest"} 1' in text
    assert "# TYPE mcm_job_runs_total counter" in text


def test_render_disconnected_flags_reconnect_now(
    clean_album_tables: sessionmaker[Session],
) -> None:
    auth = StubAuth(
        AuthStatus(connected=False, authorized_at=None, reauth_in_days=None, reauth_due=True)
    )
    text = MetricsService(repo=AlbumRepo(clean_album_tables), auth=auth).render()  # type: ignore[arg-type]
    assert "mcm_spotify_connected 0" in text
    assert "mcm_spotify_reauth_days_remaining 0" in text  # 0 = reconnect now


# --- route ----------------------------------------------------------------------------


def test_metrics_route_serves_prometheus_text(
    clean_album_tables: sessionmaker[Session],
) -> None:
    app = create_app(Settings())
    app.state.metrics_service = MetricsService(
        repo=AlbumRepo(clean_album_tables),
        auth=_connected(10),  # type: ignore[arg-type]
    )
    resp = TestClient(app).get("/metrics")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert "mcm_spotify_connected 1" in resp.text
