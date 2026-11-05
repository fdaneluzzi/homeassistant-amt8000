"""Config flow — sets up the AMT 8000 integration via UI."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .client import Amt8000Client, CannotConnect, InvalidAuth
from .const import CONF_READ_ONLY, DEFAULT_PORT, DOMAIN

_DEVICE_CLASS_OPTIONS = [
    selector.SelectOptionDict(value="", label="On/Off (default)"),
    selector.SelectOptionDict(value="door", label="Door — Open/Closed"),
    selector.SelectOptionDict(value="window", label="Window — Open/Closed"),
    selector.SelectOptionDict(value="motion", label="Motion — Detected/Clear"),
    selector.SelectOptionDict(value="smoke", label="Smoke — Detected/Clear"),
    selector.SelectOptionDict(value="vibration", label="Vibration — Detected/Clear"),
    selector.SelectOptionDict(value="garage_door", label="Garage door — Open/Closed"),
]

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_PASSWORD): str,
    }
)


class Amt8000ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return Amt8000OptionsFlow()

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

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password after the panel rejected the stored one."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            password = user_input[CONF_PASSWORD].strip()
            client = Amt8000Client(
                host=entry.data[CONF_HOST], port=entry.data[CONF_PORT], password=password
            )
            try:
                await client.get_status()
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: password}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )


class Amt8000OptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        # The entry may not be loaded (disabled or failed setup).
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        zones = coordinator.data.zones if coordinator and coordinator.data else []

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        fields: dict = {
            vol.Optional(
                CONF_READ_ONLY, default=self.config_entry.options.get(CONF_READ_ONLY, False)
            ): bool
        }
        for zone in zones:
            key = f"zone_{zone.number}_device_class"
            fields[vol.Optional(key, default=self.config_entry.options.get(key, ""))] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(options=_DEVICE_CLASS_OPTIONS)
                )
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(fields),
        )
