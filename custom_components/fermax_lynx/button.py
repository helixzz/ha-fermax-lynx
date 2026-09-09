"""Explicit controls; opening requires both gateway permission and HA enablement."""

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .api import GatewayError
from .entity import GatewayEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    permissions = coordinator.data["integration"]["permissions"]
    async_add_entities(
        [
            GatewayButton(coordinator, action, panel)
            for panel in coordinator.data["state"]["panels"]
            for action in ("preview", "hangup", "open")
            if action in permissions
        ]
    )


class GatewayButton(GatewayEntity, ButtonEntity):
    def __init__(self, coordinator, action, panel):
        super().__init__(coordinator, action, panel)
        self.action = action
        self._attr_entity_registry_enabled_default = action != "open"
        self._attr_icon = {"preview": "mdi:video", "hangup": "mdi:phone-hangup", "open": "mdi:door-open"}[action]

    @property
    def available(self):
        if not super().available or self.action not in self.permissions:
            return False
        if self.action == "preview":
            return self.gateway_state.get("call") == "idle"
        return bool(
            self.gateway_state.get("call_id")
            and self.gateway_state.get("panel_id") == self.panel["id"]
            and (self.action != "open" or self.gateway_state.get("allow_open"))
        )

    async def async_press(self):
        if not self.available:
            raise HomeAssistantError("Action unavailable for the current call")
        try:
            await self.coordinator.client.control(self.action, self.panel["id"], self.gateway_state.get("call_id"))
        except GatewayError as err:
            # Never retry: an interrupted reply does not prove the action failed.
            raise HomeAssistantError("Gateway did not confirm this request; outcome may be unknown") from err
