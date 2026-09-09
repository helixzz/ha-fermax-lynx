"""Daily confirmations do not imply physical door position."""

from homeassistant.components.sensor import SensorEntity, SensorStateClass

from .entity import GatewayEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([GatewaySensor(entry.runtime_data, key) for key in ("incoming", "openings", "call")])


class GatewaySensor(GatewayEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self.key = key
        self._attr_icon = {"incoming": "mdi:phone-incoming", "openings": "mdi:door-open", "call": "mdi:phone"}[key]
        if key != "call":
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def available(self):
        return super().available and (
            self.key == "call" or self.gateway_state.get("statistics", {}).get("available", False)
        )

    @property
    def native_value(self):
        return (
            self.gateway_state.get("call")
            if self.key == "call"
            else self.gateway_state.get("statistics", {}).get(self.key)
        )
