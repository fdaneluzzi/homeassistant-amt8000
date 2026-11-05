"""Diagnostics — lets users on untested firmware share what the panel returned."""
from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {CONF_PASSWORD, CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    raw = coordinator.client.last_status_payload if coordinator else None
    return {
        "entry": async_redact_data(
            {"data": dict(entry.data), "options": dict(entry.options)}, TO_REDACT
        ),
        "last_update_success": coordinator.last_update_success if coordinator else None,
        "status": dataclasses.asdict(coordinator.data) if coordinator and coordinator.data else None,
        # Raw 0x0B4A payload (protocol bytes only; never contains the password).
        "last_status_payload_length": len(raw) if raw is not None else None,
        "last_status_payload_hex": raw.hex(" ") if raw is not None else None,
    }
