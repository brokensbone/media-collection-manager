import json

import httpx
import respx

from wantlist.adapters.notifier import WebhookNotifier

HOOK = "https://hooks.test/abc"


@respx.mock
def test_posts_slack_shape() -> None:
    route = respx.post(HOOK).mock(return_value=httpx.Response(200))
    WebhookNotifier(HOOK).send("hello")
    assert route.called
    assert json.loads(route.calls.last.request.content) == {"text": "hello"}


@respx.mock
def test_disabled_when_no_url() -> None:
    route = respx.post(HOOK).mock(return_value=httpx.Response(200))
    WebhookNotifier("").send("nothing happens")
    assert not route.called


@respx.mock
def test_send_swallows_errors() -> None:
    respx.post(HOOK).mock(return_value=httpx.Response(500))
    WebhookNotifier(HOOK).send("boom")  # must not raise — notifications are best-effort
