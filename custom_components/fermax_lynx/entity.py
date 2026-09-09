"""Common gateway/panel device identity."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class GatewayEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, panel=None):
        super().__init__(coordinator)
        self.panel = panel
        gateway = coordinator.data["gateway"]
        gateway_id = gateway["id"]
        panel_id = panel["id"] if panel else None
        self._attr_unique_id = f"{gateway_id}_{panel_id or 'gateway'}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{gateway_id}_{panel_id}" if panel else gateway_id)},
            name=panel["name"] if panel else "FERMAX LYNX Gateway",
            manufacturer="FERMAX",
            model="LYNX gateway" if not panel else "LYNX entry panel",
            sw_version=gateway.get("version") if not panel else None,
            via_device=(DOMAIN, gateway_id) if panel else None,
        )

    @property
    def gateway_state(self):
        return self.coordinator.data["state"]

    @property
    def permissions(self):
        return self.coordinator.data["integration"]["permissions"]
