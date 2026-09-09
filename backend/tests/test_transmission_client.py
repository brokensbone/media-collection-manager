import json

import httpx
import respx

from mcm.adapters.transmission import HttpxTransmissionClient

RPC = "http://transmission.test/transmission/rpc"


def _client() -> HttpxTransmissionClient:
    return HttpxTransmissionClient(rpc_url=RPC, user="u", password="p")


@respx.mock
def test_handshake_retries_with_session_id() -> None:
    route = respx.post(RPC).mock(
        side_effect=[
            httpx.Response(409, headers={"X-Transmission-Session-Id": "sess-1"}),
            httpx.Response(
                200,
                json={
                    "arguments": {
                        "torrents": [
                            {
                                "hashString": "h1",
                                "name": "Artist - Album",
                                "downloadDir": "/downloads",
                                "percentDone": 1,
                                "files": [{"name": "Album/01.flac"}],
                            }
                        ]
                    }
                },
            ),
        ]
    )
    torrents = _client().completed_torrents()

    assert route.call_count == 2
    assert route.calls[1].request.headers["X-Transmission-Session-Id"] == "sess-1"
    assert len(torrents) == 1
    assert torrents[0].hash == "h1"
    assert torrents[0].files == ["Album/01.flac"]


@respx.mock
def test_filters_incomplete_torrents() -> None:
    respx.post(RPC).mock(
        return_value=httpx.Response(
            200,
            json={
                "arguments": {
                    "torrents": [
                        {
                            "hashString": "done",
                            "name": "A",
                            "downloadDir": "/d",
                            "percentDone": 1,
                            "files": [],
                        },
                        {
                            "hashString": "part",
                            "name": "B",
                            "downloadDir": "/d",
                            "percentDone": 0.5,
                            "files": [],
                        },
                    ]
                }
            },
        )
    )
    torrents = _client().completed_torrents()
    assert [t.hash for t in torrents] == ["done"]


@respx.mock
def test_add_torrent_base64_encodes_metainfo() -> None:
    route = respx.post(RPC).mock(return_value=httpx.Response(200, json={"result": "success"}))
    _client().add_torrent(b"d4:infodee")
    assert json.loads(route.calls[0].request.content) == {
        "method": "torrent-add",
        "arguments": {"metainfo": "ZDQ6aW5mb2RlZQ=="},
    }
