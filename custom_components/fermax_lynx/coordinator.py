"""Push lifecycle with explicit history/live boundary."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthenticationError, GatewayError
from .const import DOMAIN, EVENT_KINDS

_LOGGER = logging.getLogger(__name__)


class GatewayCoordinator(DataUpdateCoordinator):
    """One bounded reconnect loop per config entry."""

    def __init__(self, hass, entry, client):
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry)
        self.client = client
        self.entry = entry
        self.cursor = None
        self._task = None
        self._events: list[Callable] = []
        self._live = False
        self._clock_offset = 0.0
        self._seen = deque(maxlen=1024)
        self._calls = deque(maxlen=512)

    async def _async_update_data(self):
        try:
            value = await self.client.state()
            if value["gateway"]["id"] != self.entry.unique_id:
                raise AuthenticationError("Gateway identity changed")
            return value
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed("Pair this gateway again") from err
        except GatewayError as err:
            raise UpdateFailed("Gateway unavailable") from err

    def listen_events(self, callback):
        self._events.append(callback)
        return lambda: self._events.remove(callback)

    def start(self):
        # A fresh HA start deliberately begins at current head, not persisted history.
        self.cursor = self.data.get("cursor")
        self._task = self.entry.async_create_background_task(self.hass, self._run(), "FERMAX LYNX event stream")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def handle(self, kind, event_id, payload):
        if kind == "snapshot":
            self.client.validate_snapshot(payload)
            if payload.get("schema") != 1 or payload.get("gateway", {}).get("id") != self.entry.unique_id:
                raise AuthenticationError("Gateway identity changed")
            self._clock_offset = float(payload.get("server_time", time.time())) - time.time()
            self.async_set_updated_data(payload)
            # Snapshot cursor may be ahead of undelivered journal events.
        elif kind == "reset":
            self._live = False
            self.cursor = payload.get("cursor")
        elif kind == "ready":
            self.cursor = event_id or payload.get("cursor")
            self._live = True
        elif kind == "checkpoint":
            self.cursor = event_id or payload.get("cursor")
        elif kind == "event":
            previous = self.cursor
            self.cursor = event_id or payload.get("id")
            if (
                self._live
                and payload.get("replayed") is False
                and self.cursor != previous
                and self.cursor not in self._seen
                and payload.get("kind") in EVENT_KINDS
                and self._fresh(payload)
            ):
                self._seen.append(self.cursor)
                if payload["kind"] == "incoming":
                    call = payload.get("call_id")
                    if call and call in self._calls:
                        return
                    if call:
                        self._calls.append(call)
                for callback in tuple(self._events):
                    callback(payload)

    def _fresh(self, payload):
        try:
            timestamp = payload["time"]
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
            age = time.time() + self._clock_offset - float(timestamp)
            return -5 <= age <= 30
        except KeyError, TypeError, ValueError:
            return False

    async def _run(self):
        delay = 1
        while True:
            self._live = False
            try:
                async for message in self.client.events(self.cursor):
                    self.handle(*message)
                    if self._live:
                        delay = 1
                raise GatewayError("Gateway event stream ended")
            except AuthenticationError:
                self.async_set_update_error(UpdateFailed("Gateway authorization expired"))
                self.entry.async_start_reauth(self.hass)
                return
            except GatewayError:
                self.async_set_update_error(UpdateFailed("Gateway disconnected"))
            await asyncio.sleep(delay + random.uniform(0, delay / 4))
            delay = min(delay * 2, 60)
