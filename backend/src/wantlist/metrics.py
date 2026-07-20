from collections.abc import Sequence

from .adapters.album_repo import AlbumRepo
from .auth_service import AuthService
from .models import AlbumState

# Prometheus 0.0.4 text exposition. Content-type set by the router.
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class MetricsService:
    """Renders `/metrics` (SPEC §16, D18). Everything is read from the DB so the API process
    reports the worker process's liveness too — the whole point of the `job_run` heartbeat.
    Series are always emitted (0 when absent) so Grafana alert rules have a stable target."""

    def __init__(self, *, repo: AlbumRepo, auth: AuthService) -> None:
        self._repo = repo
        self._auth = auth

    def render(self) -> str:
        lines: list[str] = []

        status = self._auth.status()
        _gauge(
            lines,
            "wantlist_spotify_connected",
            "Spotify refresh token present (1) or reconnect needed (0).",
            [("", 1 if status.connected else 0)],
        )
        # 0 == reconnect now (disconnected or already past expiry) so the alert still fires.
        days = status.reauth_in_days if status.reauth_in_days is not None else 0
        _gauge(
            lines,
            "wantlist_spotify_reauth_days_remaining",
            "Days until the Spotify refresh token expires; 0 = reconnect now.",
            [("", max(days, 0))],
        )

        counts = self._repo.count_by_state()
        _gauge(
            lines,
            "wantlist_albums",
            "Albums in each funnel state.",
            [(f'state="{s.value}"', counts.get(s.value, 0)) for s in AlbumState],
        )
        _gauge(
            lines,
            "wantlist_albums_missing_art",
            "Albums with a source art URL but no stored cover blob yet.",
            [("", self._repo.count_missing_art())],
        )
        resolved, unresolved = self._repo.resolution_counts()
        _gauge(
            lines,
            "wantlist_albums_resolution",
            "Albums by MusicBrainz release-group resolution state (cold-start progress).",
            [('state="resolved"', resolved), ('state="unresolved"', unresolved)],
        )

        runs = self._repo.job_runs()
        _gauge(
            lines,
            "wantlist_job_last_success_timestamp",
            "Unix time of each poller's last successful run; 0 = never. Alert on staleness.",
            [
                (f'job="{r.job}"', int(r.last_success_at.timestamp()) if r.last_success_at else 0)
                for r in runs
            ],
        )
        _counter(
            lines,
            "wantlist_job_runs_total",
            "Total successful runs per poller.",
            [(f'job="{r.job}"', r.runs) for r in runs],
        )
        _counter(
            lines,
            "wantlist_job_errors_total",
            "Total errored runs per poller.",
            [(f'job="{r.job}"', r.errors) for r in runs],
        )
        return "\n".join(lines) + "\n"


def _gauge(lines: list[str], name: str, help_: str, samples: Sequence[tuple[str, float]]) -> None:
    _metric(lines, name, "gauge", help_, samples)


def _counter(lines: list[str], name: str, help_: str, samples: Sequence[tuple[str, int]]) -> None:
    _metric(lines, name, "counter", help_, samples)


def _metric(
    lines: list[str], name: str, kind: str, help_: str, samples: Sequence[tuple[str, float]]
) -> None:
    lines.append(f"# HELP {name} {help_}")
    lines.append(f"# TYPE {name} {kind}")
    for labels, value in samples:
        series = f"{name}{{{labels}}}" if labels else name
        lines.append(f"{series} {value}")
