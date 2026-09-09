from datetime import UTC, datetime, timedelta

from mcm.domain.auth import compute_status

NOW = datetime(2026, 7, 16, tzinfo=UTC)


def test_disconnected_when_not_connected() -> None:
    s = compute_status(
        connected=False, authorized_at=None, now=NOW, lifetime_days=183, warn_days=21
    )
    assert s.connected is False
    assert s.reauth_in_days is None
    assert s.reauth_due is True


def test_connected_counts_down_to_reauth() -> None:
    s = compute_status(
        connected=True,
        authorized_at=NOW - timedelta(days=100),
        now=NOW,
        lifetime_days=183,
        warn_days=21,
    )
    assert s.connected is True
    assert s.reauth_in_days == 83
    assert s.reauth_due is False


def test_reauth_due_within_warning_window() -> None:
    s = compute_status(
        connected=True,
        authorized_at=NOW - timedelta(days=170),
        now=NOW,
        lifetime_days=183,
        warn_days=21,
    )
    assert s.reauth_in_days == 13
    assert s.reauth_due is True
