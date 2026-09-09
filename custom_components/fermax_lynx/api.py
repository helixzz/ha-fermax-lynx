"""Small asynchronous client; no retries for potentially physical controls."""

from __future__ import annotations

import json
import time
from urllib.parse import urlsplit
from uuid import uuid4

import aiohttp


class GatewayError(Exception):
    """A sanitized gateway failure."""


class AuthenticationError(GatewayError):
    """Credential invalid or revoked."""


class ProtocolError(GatewayError):
    """Unsupported or malformed protocol."""


def validate_url(value: str) -> str:
    """Accept only a gateway origin; preserve TLS certificate verification."""
    try:
        url = urlsplit(value.strip())
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path not in ("", "/")
            or url.port == 0
        ):
            raise ValueError
        return f"{url.scheme}://{url.netloc}".rstrip("/")
    except (ValueError, AttributeError) as err:
        raise ValueError("Invalid gateway URL") from err


class GatewayClient:
    """Integration-only API; redirects never receive the bearer credential."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: str = ""):
        self.session = session
        self.url = validate_url(url)
        self.token = token

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @staticmethod
    def check(response):
        if response.status in (401, 403):
            raise AuthenticationError("Gateway authentication failed")
        if response.status >= 300:
            raise GatewayError(f"Gateway request failed ({response.status})")

    async def request(self, method, path, **kwargs):
        try:
            async with self.session.request(
                method,
                f"{self.url}/v1/integration/{path}",
                headers=self.headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=15),
                **kwargs,
            ) as response:
                self.check(response)
                result = await response.json()
                if not isinstance(result, dict):
                    raise ProtocolError("Invalid gateway response")
                return result
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise GatewayError("Gateway connection failed") from err

    async def pair(self, code):
        result = await self.request("POST", "pair", json={"code": code})
        if result.get("schema") != 1 or not result.get("token") or not result.get("gateway", {}).get("id"):
            raise ProtocolError("Unsupported gateway response")
        return result

    @staticmethod
    def validate_snapshot(result):
        """Fail closed on incompatible data rather than killing the stream task."""
        try:
            state = result["state"]
            permissions = result["integration"]["permissions"]
            valid = (
                result["schema"] == 1
                and isinstance(result["gateway"]["id"], str)
                and isinstance(result["cursor"], str)
                and isinstance(result["server_time"], (int, float))
                and isinstance(state, dict)
                and isinstance(state["statistics"], dict)
                and isinstance(state["auto"], dict)
                and isinstance(state["panels"], list)
                and all(isinstance(p["id"], str) and isinstance(p["name"], str) for p in state["panels"])
                and isinstance(permissions, list)
                and all(isinstance(p, str) for p in permissions)
            )
            if not valid:
                raise ProtocolError("Unsupported gateway response")
        except (KeyError, TypeError) as err:
            raise ProtocolError("Unsupported gateway response") from err
        return result

    async def state(self):
        return self.validate_snapshot(await self.request("GET", "state"))

    async def control(self, action, panel, call_id):
        return await self.request(
            "POST",
            "control",
            json={
                "action": action,
                "panel": panel,
                "call_id": call_id,
                "request_id": str(uuid4()),
                "expires_at": time.time() + 10,
            },
        )

    async def frame(self, panel):
        try:
            async with self.session.get(
                f"{self.url}/v1/integration/frame.jpg",
                params={"panel": panel},
                headers=self.headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 404:
                    return None
                self.check(response)
                if response.content_type != "image/jpeg":
                    raise ProtocolError("Invalid image response")
                image = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    image.extend(chunk)
                    if len(image) > 2_000_000:
                        raise ProtocolError("Image exceeds limit")
                return bytes(image)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GatewayError("Gateway image unavailable") from err

    async def events(self, cursor):
        headers = self.headers
        if cursor:
            headers["Last-Event-ID"] = cursor
        try:
            async with self.session.get(
                f"{self.url}/v1/integration/events",
                headers=headers,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=40),
            ) as response:
                self.check(response)
                if response.content_type != "text/event-stream":
                    raise ProtocolError("Invalid event stream")
                kind, event_id, data, size = "message", None, [], 0
                async for line in response.content:
                    size += len(line)
                    if size > 262144:
                        raise ProtocolError("Event exceeds limit")
                    text = line.decode("utf-8").rstrip("\r\n")
                    if not text:
                        if data:
                            value = json.loads("\n".join(data))
                            if not isinstance(value, dict):
                                raise ProtocolError("Invalid event")
                            yield kind, event_id, value
                        kind, event_id, data, size = "message", None, [], 0
                    elif text.startswith("event:"):
                        kind = text[6:].lstrip(" ")
                    elif text.startswith("id:"):
                        event_id = text[3:].lstrip(" ")
                    elif text.startswith("data:"):
                        data.append(text[5:].lstrip(" "))
        except (aiohttp.ClientError, TimeoutError, ValueError, UnicodeError) as err:
            raise GatewayError("Gateway event stream interrupted") from err
