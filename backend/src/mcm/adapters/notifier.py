import logging

import httpx

log = logging.getLogger(__name__)


class WebhookNotifier:
    """POSTs a Slack-compatible {"text": ...} to a webhook. Empty URL = disabled no-op,
    so notifications are simply off until a webhook is configured (§8d)."""

    def __init__(self, url: str) -> None:
        self._url = url

    def send(self, text: str) -> None:
        if not self._url:
            return
        try:
            httpx.post(self._url, json={"text": text}, timeout=10).raise_for_status()
        except Exception:
            log.exception("notification send failed")
