"""Config flow — sets up the AMT 8000 integration via UI."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .client import Amt8000Client, CannotConnect, InvalidAuth
from .const import DEFAULT_PORT, DOMAIN

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


class Amt8000OptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        zones = coordinator.data.zones if coordinator.data else []

        if user_input is not None:
            return self.async_create_entry(data=user_input)

        fields: dict = {}
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
