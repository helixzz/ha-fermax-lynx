"""Real Home Assistant fixtures, synthetic gateway only."""

import time

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def snapshot():
    return {
        "schema": 1,
        "server_time": time.time(),
        "gateway": {"id": "synthetic-gateway", "version": "0.7.0"},
        "integration": {
            "id": "synthetic-integration",
            "permissions": ["state", "events", "camera", "preview", "hangup", "open"],
        },
        "cursor": "journal:10",
        "state": {
            "network": "ready",
            "call": "idle",
            "call_id": None,
            "panel_id": None,
            "panels": [{"id": "synthetic-panel", "name": "Example entry"}],
            "allow_open": False,
            "video_ready": False,
            "statistics": {"date": "2026-09-09", "available": True, "incoming": 2, "openings": 1},
            "auto": {"enabled": False},
        },
    }
