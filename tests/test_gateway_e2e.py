"""Optional contract test against the sibling gateway's loopback-only fixture.

FERMAX_GATEWAY_SOURCE=/path/to/fermax-lynx-gateway pytest tests/test_gateway_e2e.py
Never accepts a deployed gateway URL.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import aiohttp
import pytest

from custom_components.fermax_lynx.api import AuthenticationError, GatewayClient, GatewayError


@pytest.mark.skipif(not os.environ.get("FERMAX_GATEWAY_SOURCE"), reason="Optional sibling source checkout required")
@pytest.mark.enable_socket
async def test_real_gateway_contract():
    source = Path(os.environ["FERMAX_GATEWAY_SOURCE"]).resolve()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.phone_fixture",
        cwd=source,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(source)},
    )
    try:
        line = await asyncio.wait_for(process.stdout.readline(), 15)
        assert line, "Synthetic fixture did not start"
        port = json.loads(line)["port"]
        url = f"http://127.0.0.1:{port}"
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            async with session.post(url + "/v1/login", json={"password": "synthetic-phone-password"}) as response:
                assert response.status == 200
            async with session.post(
                url + "/v1/integrations/pairing",
                json={
                    "password": "synthetic-phone-password",
                    "name": "Synthetic HA contract test",
                    "panels": ["entrance"],
                    "permissions": ["state", "events", "camera", "preview", "hangup"],
                },
            ) as response:
                assert response.status == 200
                code = (await response.json())["code"]
            client = GatewayClient(session, url)
            paired = await client.pair(code)
            client.token = paired["token"]
            snapshot = await client.state()
            assert snapshot["state"]["call"] == "idle"
            assert snapshot["state"]["panels"] == [{"id": "entrance", "name": "花园入口"}]
            stream = client.events(snapshot["cursor"])
            assert (await anext(stream))[0] == "snapshot"
            while (await anext(stream))[0] != "ready":
                pass
            process.stdin.write(b'{"command":"incoming"}\n')
            await process.stdin.drain()
            await process.stdout.readline()
            async with asyncio.timeout(10):
                async for kind, event_id, event in stream:
                    if kind == "event" and event["kind"] == "incoming":
                        assert event["replayed"] is False
                        assert event["call_id"] and event_id
                        break
            current = await client.state()
            image = await client.frame("entrance")
            assert image.startswith(b"\xff\xd8")
            with pytest.raises(GatewayError):
                await client.control("open", "entrance", current["state"]["call_id"])
            await client.control("hangup", "entrance", current["state"]["call_id"])
            assert (await client.state())["state"]["call"] == "idle"
            await stream.aclose()
            async with session.post(
                url + "/v1/integrations/revoke",
                json={
                    "password": "synthetic-phone-password",
                    "id": paired["integration"]["id"],
                },
            ) as response:
                assert response.status == 200
            with pytest.raises(AuthenticationError):
                await client.state()
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 10)
        except TimeoutError:
            process.kill()
            await process.wait()
