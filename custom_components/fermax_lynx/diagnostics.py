"""Allowlist diagnostics: never serialize credentials or household identifiers."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "integration_version": "0.1.0",
        "gateway_version": coordinator.data.get("gateway", {}).get("version"),
        "schema": coordinator.data.get("schema"),
        "available": coordinator.last_update_success,
        "permissions": coordinator.data.get("integration", {}).get("permissions", []),
        "panel_count": len(coordinator.data.get("state", {}).get("panels", [])),
    }
