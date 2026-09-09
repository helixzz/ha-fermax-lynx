"""Pair without storing a gateway administrator password or pairing code."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthenticationError, GatewayClient, GatewayError, ProtocolError, validate_url
from .const import DOMAIN


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return await self._pair("user", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._pair("reauth_confirm", user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._pair("reconfigure", user_input)

    async def _pair(self, step, user_input):
        errors = {}
        entry = None
        if step == "reauth_confirm":
            entry = self._get_reauth_entry()
        elif step == "reconfigure":
            entry = self._get_reconfigure_entry()
        if user_input is not None:
            try:
                url = validate_url(user_input["url"])
                result = await GatewayClient(async_get_clientsession(self.hass), url).pair(user_input["code"])
                gateway_id = result["gateway"]["id"]
                if entry and gateway_id != entry.unique_id:
                    return self.async_abort(reason="wrong_gateway")
                await self.async_set_unique_id(gateway_id)
                data = {"url": url, "token": result["token"]}
                if entry:
                    return self.async_update_reload_and_abort(entry, data_updates=data)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="FERMAX LYNX Gateway", data=data)
            except ValueError:
                errors["url"] = "invalid_url"
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except ProtocolError:
                errors["base"] = "unsupported_gateway"
            except GatewayError:
                errors["base"] = "cannot_connect"
        schema = vol.Schema(
            {
                vol.Required("url", default=entry.data["url"] if entry else "http://gateway.local:8080"): str,
                vol.Required("code"): str,
            }
        )
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)
