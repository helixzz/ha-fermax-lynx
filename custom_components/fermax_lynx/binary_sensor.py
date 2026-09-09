"""Connection and automatic opening policy state."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .entity import GatewayEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([GatewayBinarySensor(entry.runtime_data, key) for key in ("network", "auto")])


class GatewayBinarySensor(GatewayEntity, BinarySensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self.key = key
        self._attr_icon = "mdi:door-open" if key == "auto" else "mdi:lan-connect"
        if key == "network":
            self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self):
        if self.key == "auto":
            return self.gateway_state.get("auto", {}).get("enabled", False)
        return self.gateway_state.get("network") == "ready"
