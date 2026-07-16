from datetime import UTC, datetime

from wantlist.domain.verdict import forgotten_reason


def test_forgotten_reason_reports_days_since_saved() -> None:
    saved = datetime(2026, 6, 16, tzinfo=UTC)
    now = datetime(2026, 7, 16, tzinfo=UTC)
    assert forgotten_reason(saved, now) == "saved 30d ago"
