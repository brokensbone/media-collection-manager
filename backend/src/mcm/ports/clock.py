from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Injectable clock (SPEC §14): time-based logic never calls the system clock directly."""

    def now(self) -> datetime: ...
