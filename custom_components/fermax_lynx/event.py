"""Only fresh, live events are eligible for automations."""

from homeassistant.components.event import DoorbellEventType, EventDeviceClass, EventEntity

from .const import EVENT_KINDS
from .entity import GatewayEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [
            GatewayEvent(coordinator, key, panel)
            for panel in coordinator.data["state"]["panels"]
            for key in ("doorbell", "activity")
        ]
    )


class GatewayEvent(GatewayEntity, EventEntity):
    def __init__(self, coordinator, key, panel):
        super().__init__(coordinator, key, panel)
        self.key = key
        self._attr_event_types = [DoorbellEventType.RING] if key == "doorbell" else EVENT_KINDS
        if key == "doorbell":
            self._attr_device_class = EventDeviceClass.DOORBELL

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.listen_events(self._handle))

    def _handle(self, event):
        if event.get("panel_id") != self.panel["id"]:
            return
        if self.key == "doorbell":
            if event["kind"] != "incoming":
                return
            event_type = DoorbellEventType.RING
        else:
            if event["kind"] not in self._attr_event_types:
                return
            event_type = event["kind"]
        self._trigger_event(
            event_type,
            {"event_id": event["id"], "call_id": event.get("call_id"), "request_id": event.get("request_id")},
        )
        self.async_write_ha_state()
        if self.key == "doorbell":
            self.hass.bus.async_fire("fermax_lynx_doorbell", {"entity_id": self.entity_id, "event_id": event["id"]})
