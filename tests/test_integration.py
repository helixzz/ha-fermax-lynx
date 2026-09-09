"""Exercise actual HA config entries, entities, event lifecycle and authentication."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fermax_lynx.api import AuthenticationError, GatewayError, validate_url
from custom_components.fermax_lynx.const import DOMAIN
from custom_components.fermax_lynx.diagnostics import async_get_config_entry_diagnostics


async def silent_stream(self, cursor):
    await asyncio.Event().wait()
    yield None


async def setup(hass, snapshot):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test gateway",
        unique_id="synthetic-gateway",
        data={"url": "http://192.0.2.1:8080", "token": "synthetic-token"},
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.fermax_lynx.api.GatewayClient.state", return_value=snapshot),
        patch("custom_components.fermax_lynx.api.GatewayClient.events", silent_stream),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_flow(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    pair = {"schema": 1, "gateway": {"id": "synthetic-gateway"}, "token": "synthetic-token"}
    with (
        patch("custom_components.fermax_lynx.api.GatewayClient.pair", return_value=pair),
        patch("custom_components.fermax_lynx.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"url": "http://192.0.2.1:8080", "code": "synthetic-code"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"url": "http://192.0.2.1:8080", "token": "synthetic-token"}


@pytest.mark.parametrize(
    "error,expected", [(AuthenticationError(), "invalid_auth"), (GatewayError(), "cannot_connect")]
)
async def test_flow_error(hass, error, expected):
    with patch("custom_components.fermax_lynx.api.GatewayClient.pair", side_effect=error):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data={"url": "http://192.0.2.1", "code": "invalid"}
        )
    assert result["errors"] == {"base": expected}


async def test_setup_permissions_events_unload(hass, snapshot):
    entry = await setup(hass, snapshot)
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    opening = next(e for e in entities if e.unique_id.endswith("_open"))
    assert opening.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert len(entities) == 11
    assert hass.states.get(next(e.entity_id for e in entities if e.unique_id.endswith("_incoming"))).state == "2"
    calls = []
    remove = coordinator.listen_events(calls.append)
    coordinator.handle("snapshot", None, {**snapshot, "cursor": "journal:999"})
    assert coordinator.cursor == "journal:10"
    event = {
        "id": "journal:11",
        "kind": "incoming",
        "panel_id": "synthetic-panel",
        "call_id": "call-1",
        "replayed": True,
        "time": time.time(),
    }
    coordinator.handle("event", "journal:11", event)
    assert not calls
    coordinator.handle("ready", "journal:11", {})
    live = {**event, "id": "journal:12", "replayed": False}
    coordinator.handle("event", "journal:12", live)
    coordinator.handle("event", "journal:12", live)
    coordinator.handle("event", "journal:13", {**live, "id": "journal:13"})
    assert len(calls) == 1
    coordinator.handle("event", "journal:14", {**live, "id": "journal:14", "call_id": "old", "time": time.time() - 90})
    assert len(calls) == 1
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "synthetic" not in str(diagnostics) and "token" not in str(diagnostics)
    remove()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator._task is None


async def test_permissions_absent(hass, snapshot):
    snapshot["integration"]["permissions"] = ["state", "events"]
    entry = await setup(hass, snapshot)
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert not any(e.domain in ("button", "camera") for e in entities)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reauth_wrong_gateway(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="original", data={"url": "http://192.0.2.1", "token": "old"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id}, data=entry.data
    )
    with patch(
        "custom_components.fermax_lynx.api.GatewayClient.pair",
        return_value={"gateway": {"id": "other"}, "token": "new"},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"url": "http://192.0.2.2", "code": "code"}
        )
    assert result["reason"] == "wrong_gateway"
    assert entry.data["token"] == "old"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "http://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?token=x",
        "http://example.com:0",
    ],
)
def test_bad_urls(url):
    with pytest.raises(ValueError):
        validate_url(url)


@pytest.mark.parametrize("source", [config_entries.SOURCE_REAUTH, config_entries.SOURCE_RECONFIGURE])
async def test_update_flow(hass, source):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="original", data={"url": "http://192.0.2.1", "token": "old"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": source, "entry_id": entry.entry_id},
        data=entry.data if source == config_entries.SOURCE_REAUTH else None,
    )
    with (
        patch(
            "custom_components.fermax_lynx.api.GatewayClient.pair",
            return_value={"gateway": {"id": "original"}, "token": "new"},
        ),
        patch("custom_components.fermax_lynx.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"url": "http://192.0.2.2", "code": "code"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert entry.data == {"url": "http://192.0.2.2", "token": "new"}


async def test_disconnect_auth_lifecycle(hass, snapshot):
    entry = await setup(hass, snapshot)
    coordinator = entry.runtime_data
    await coordinator.stop()
    observed = []

    async def disconnected(cursor):
        observed.append(cursor)
        if len(observed) == 1:
            raise GatewayError("synthetic disconnect")
        raise AuthenticationError("synthetic revoked")
        yield

    with (
        patch.object(coordinator.client, "events", disconnected),
        patch("custom_components.fermax_lynx.coordinator.asyncio.sleep", new=AsyncMock()),
        patch.object(entry, "async_start_reauth") as reauth,
    ):
        await coordinator._run()
        reauth.assert_called_once_with(hass)
    assert observed == ["journal:10", "journal:10"]
    assert not coordinator.last_update_success
    await hass.config_entries.async_unload(entry.entry_id)


async def test_controls_and_camera(hass, snapshot):
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.fermax_lynx.button import GatewayButton
    from custom_components.fermax_lynx.camera import GatewayCamera

    entry = await setup(hass, snapshot)
    coordinator = entry.runtime_data
    panel = snapshot["state"]["panels"][0]
    button = GatewayButton(coordinator, "open", panel)
    camera = GatewayCamera(coordinator, "camera", panel)
    with (
        patch.object(coordinator.client, "control", new=AsyncMock()) as control,
        patch.object(coordinator.client, "frame", new=AsyncMock(return_value=b"JPEG")) as frame,
    ):
        with pytest.raises(HomeAssistantError):
            await button.async_press()
        assert await camera.async_camera_image() is None
        control.assert_not_called()
        frame.assert_not_called()
        snapshot["state"].update(
            call="ringing", call_id="call-A", panel_id=panel["id"], allow_open=True, video_ready=True
        )
        await button.async_press()
        control.assert_awaited_once_with("open", panel["id"], "call-A")
        assert await camera.async_camera_image() == b"JPEG"
        frame.assert_awaited_once_with(panel["id"])
        control.side_effect = GatewayError("unknown")
        with pytest.raises(HomeAssistantError, match="unknown"):
            await button.async_press()
        assert control.await_count == 2  # exactly one request per press; never retried
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("wall_jump", [-86400, 86400])
async def test_event_freshness_uses_monotonic_clock(hass, snapshot, wall_jump):
    entry = await setup(hass, snapshot)
    coordinator = entry.runtime_data
    sample = snapshot["server_time"]
    with patch("custom_components.fermax_lynx.coordinator.time.monotonic", return_value=1000):
        coordinator.handle("snapshot", None, snapshot)
    with (
        patch("custom_components.fermax_lynx.coordinator.time.time", return_value=sample + wall_jump),
        patch("custom_components.fermax_lynx.coordinator.time.monotonic", return_value=1020),
    ):
        assert coordinator._fresh({"time": sample})
        assert not coordinator._fresh({"time": sample - 15})
        assert not coordinator._fresh({"time": sample + 30})
    await hass.config_entries.async_unload(entry.entry_id)


async def test_heartbeat_refreshes_clock_and_checks_identity(hass, snapshot):
    entry = await setup(hass, snapshot)
    coordinator = entry.runtime_data
    cursor = coordinator.cursor
    heartbeat = {**snapshot, "server_time": snapshot["server_time"] + 100, "cursor": "journal:999"}
    with patch("custom_components.fermax_lynx.coordinator.time.monotonic", return_value=2000):
        coordinator.handle("heartbeat", None, heartbeat)
        assert coordinator._fresh({"time": heartbeat["server_time"]})
        assert not coordinator._fresh({"time": snapshot["server_time"]})
    assert coordinator.cursor == cursor
    with pytest.raises(AuthenticationError):
        coordinator.handle("heartbeat", None, {**heartbeat, "gateway": {"id": "wrong-gateway"}})
    with pytest.raises(GatewayError):
        coordinator.handle("heartbeat", None, {**heartbeat, "schema": 2})
    await hass.config_entries.async_unload(entry.entry_id)
