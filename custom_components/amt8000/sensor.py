"""Diagnostic sensors — panel battery level."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .alarm_control_panel import _device_info
from .const import DOMAIN
from .coordinator import Amt8000Coordinator

BATTERY_LEVELS = ["dead", "low", "middle", "full"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: Amt8000Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Amt8000BatterySensor(coordinator, entry)])


class Amt8000BatterySensor(CoordinatorEntity[Amt8000Coordinator], SensorEntity):
    """Backup battery level as reported by the panel (dead/low/middle/full)."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = BATTERY_LEVELS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Amt8000Coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_battery"
        self._attr_name = "Battery"
        self._attr_device_info = _device_info(entry, coordinator.data)

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        level = self.coordinator.data.battery
        return level if level in BATTERY_LEVELS else None
