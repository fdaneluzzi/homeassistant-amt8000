"""Switches for AMT 8000 PGM outputs and per-zone bypass.

EXPERIMENTAL: these entities rely on protocol commands (0x0B50, 0x40 1F,
0x45 AF) that have not been verified against a real AMT 8000 panel by the
maintainer, unlike the rest of this integration. If a command is rejected
or the panel misbehaves, please open an issue with the debug log
(Settings -> Logs, filter by custom_components.amt8000).
"""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .alarm_control_panel import _device_info
from .client import BypassError, PgmError
from .const import DOMAIN
from .coordinator import Amt8000Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: Amt8000Coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [
        Amt8000ZoneBypassSwitch(coordinator, zone.number, entry)
        for zone in coordinator.data.zones
    ]
    entities.extend(
        Amt8000PgmSwitch(coordinator, pgm.index, entry) for pgm in coordinator.data.pgms
    )
    async_add_entities(entities)


class Amt8000ZoneBypassSwitch(CoordinatorEntity[Amt8000Coordinator], SwitchEntity):
    """Bypass (anular) or restore a single zone."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:electric-switch"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: Amt8000Coordinator, zone_number: int, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._zone_number = zone_number
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone_number}_bypass"
        self._attr_name = f"Zone {zone_number} bypass"
        self._attr_device_info = _device_info(entry)

    def _zone(self):
        if not self.coordinator.data:
            return None
        for zone in self.coordinator.data.zones:
            if zone.number == self._zone_number:
                return zone
        return None

    @property
    def is_on(self) -> bool | None:
        zone = self._zone()
        return zone.bypassed if zone else None

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._set_bypass(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._set_bypass(False)

    async def _set_bypass(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.bypass_zone(self._zone_number - 1, enabled)
        except BypassError as exc:
            raise HomeAssistantError(
                f"Panel rejected bypass for zone {self._zone_number}: {exc}"
            ) from exc
        await self.coordinator.async_request_refresh()


class Amt8000PgmSwitch(CoordinatorEntity[Amt8000Coordinator], SwitchEntity):
    """Turn a PGM (auxiliary output) on or off."""

    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: Amt8000Coordinator, pgm_index: int, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._pgm_index = pgm_index
        self._number = pgm_index + 1
        self._attr_unique_id = f"{entry.entry_id}_pgm_{self._number}"
        self._attr_name = f"PGM {self._number}"
        self._attr_device_info = _device_info(entry)

    def _pgm(self):
        if not self.coordinator.data:
            return None
        for pgm in self.coordinator.data.pgms:
            if pgm.index == self._pgm_index:
                return pgm
        return None

    @property
    def icon(self) -> str:
        return "mdi:electric-switch" if self.is_on else "mdi:electric-switch-closed"

    @property
    def is_on(self) -> bool | None:
        pgm = self._pgm()
        return pgm.on if pgm else None

    @property
    def extra_state_attributes(self) -> dict:
        pgm = self._pgm()
        if pgm is None:
            return {}
        return {
            "tamper": pgm.tamper,
            "low_battery": pgm.low_battery,
            "comm_fail": pgm.comm_fail,
        }

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._set_pgm(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._set_pgm(False)

    async def _set_pgm(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.set_pgm(self._pgm_index, enabled)
        except PgmError as exc:
            raise HomeAssistantError(f"Panel rejected PGM {self._number} command: {exc}") from exc
        await self.coordinator.async_request_refresh()
