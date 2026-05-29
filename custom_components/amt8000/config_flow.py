"""Config flow — sets up the AMT 8000 integration via UI."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT

from .client import Amt8000Client, CannotConnect, InvalidAuth
from .const import DEFAULT_PORT, DOMAIN

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_PASSWORD): str,
    }
)


class Amt8000ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            password = user_input[CONF_PASSWORD].strip()

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            client = Amt8000Client(host=host, port=port, password=password)
            try:
                await client.get_status()
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"AMT 8000 ({host})",
                    data={CONF_HOST: host, CONF_PORT: port, CONF_PASSWORD: password},
                )

        return self.async_show_form(step_id="user", data_schema=_SCHEMA, errors=errors)
