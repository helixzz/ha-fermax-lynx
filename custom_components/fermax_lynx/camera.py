"""Current JPEG only: polling never starts a preview."""

from homeassistant.components.camera import Camera

from .api import GatewayError
from .entity import GatewayEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    if "camera" in coordinator.data["integration"]["permissions"]:
        async_add_entities(
            [GatewayCamera(coordinator, "camera", panel) for panel in coordinator.data["state"]["panels"]]
        )


class GatewayCamera(GatewayEntity, Camera):
    def __init__(self, coordinator, key, panel):
        Camera.__init__(self)
        GatewayEntity.__init__(self, coordinator, key, panel)

    @property
    def available(self):
        return (
            super().available
            and "camera" in self.permissions
            and self.gateway_state.get("video_ready", False)
            and self.gateway_state.get("panel_id") == self.panel["id"]
        )

    async def async_camera_image(self, width=None, height=None):
        if not self.available:
            return None
        try:
            return await self.coordinator.client.frame(self.panel["id"])
        except GatewayError:
            return None
