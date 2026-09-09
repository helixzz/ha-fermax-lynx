"""FERMAX LYNX Gateway local push integration."""

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GatewayClient
from .const import PLATFORMS
from .coordinator import GatewayCoordinator


async def async_setup_entry(hass, entry):
    client = GatewayClient(async_get_clientsession(hass), entry.data["url"], entry.data["token"])
    coordinator = GatewayCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start()
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.stop()
        return True
    return False
