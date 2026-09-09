from datetime import UTC, datetime


class SystemClock:
    """Real clock. Tests use a frozen clock implementing the same Clock port."""

    def now(self) -> datetime:
        return datetime.now(UTC)
