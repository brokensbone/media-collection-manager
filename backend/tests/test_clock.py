from datetime import UTC, datetime

from mcm.adapters.clock import SystemClock
from mcm.ports.clock import Clock


class FrozenClock:
    """Test double: satisfies the Clock port with a fixed time."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed


def test_system_clock_is_timezone_aware_utc() -> None:
    assert SystemClock().now().tzinfo == UTC


def test_frozen_clock_satisfies_port() -> None:
    clock: Clock = FrozenClock(datetime(2026, 7, 16, tzinfo=UTC))
    assert clock.now().year == 2026
