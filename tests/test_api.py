"""Real aiohttp requests to synthetic responses, including SSE framing."""

import json

import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.fermax_lynx.api import AuthenticationError, GatewayClient, GatewayError


async def test_requests(hass, aioclient_mock, snapshot):
    url = "http://192.0.2.1"
    client = GatewayClient(async_get_clientsession(hass), url, "synthetic-token")
    aioclient_mock.get(url + "/v1/integration/state", json=snapshot)
    assert await client.state() == snapshot
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "Bearer synthetic-token"
    aioclient_mock.post(url + "/v1/integration/control", json={"ok": True})
    await client.control("open", "synthetic-panel", "synthetic-call")
    body = aioclient_mock.mock_calls[-1][2]
    assert body["action"] == "open" and body["call_id"] == "synthetic-call"
    assert body["request_id"] and body["expires_at"]


async def test_redirect_auth_and_no_retry(hass, aioclient_mock):
    client = GatewayClient(async_get_clientsession(hass), "http://192.0.2.1", "synthetic-token")
    aioclient_mock.get(
        "http://192.0.2.1/v1/integration/state", status=302, headers={"Location": "http://192.0.2.2/steal"}
    )
    with pytest.raises(GatewayError):
        await client.state()
    assert aioclient_mock.call_count == 1
    aioclient_mock.post("http://192.0.2.1/v1/integration/control", status=401)
    with pytest.raises(AuthenticationError):
        await client.control("open", "panel", "call")
    assert aioclient_mock.call_count == 2


async def test_sse(hass, aioclient_mock, snapshot):
    client = GatewayClient(async_get_clientsession(hass), "http://192.0.2.1", "synthetic-token")
    data = f': heartbeat\n\nevent: snapshot\ndata: {json.dumps(snapshot)}\n\nevent: ready\nid: journal:10\ndata: {{"cursor":"journal:10"}}\n\n'
    aioclient_mock.get(
        "http://192.0.2.1/v1/integration/events", text=data, headers={"Content-Type": "text/event-stream"}
    )
    messages = [item async for item in client.events("journal:9")]
    assert messages[0] == ("snapshot", None, snapshot)
    assert messages[1] == ("ready", "journal:10", {"cursor": "journal:10"})
    assert aioclient_mock.mock_calls[0][3]["Last-Event-ID"] == "journal:9"


@pytest.mark.parametrize("payload", [{}, {"schema": 1, "state": []}, {"schema": 2}])
def test_malformed_snapshot(payload):
    with pytest.raises(GatewayError):
        GatewayClient.validate_snapshot(payload)
