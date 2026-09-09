from typing import Protocol


class NotificationSender(Protocol):
    """Send a short human message to wherever the operator watches (SPEC §8d)."""

    def send(self, text: str) -> None: ...
