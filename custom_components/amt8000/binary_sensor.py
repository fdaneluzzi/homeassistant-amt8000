"""Binary sensors — one per zone plus a siren sensor."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .alarm_control_panel import _device_info
from .const import DOMAIN
from .coordinator import Amt8000Coordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: Amt8000Coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        Amt8000ZoneSensor(coordinator, zone.number, entry)
        for zone in coordinator.data.zones
    ]
    entities.append(Amt8000SirenSensor(coordinator, entry))
    async_add_entities(entities)


class Amt8000ZoneSensor(CoordinatorEntity[Amt8000Coordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: Amt8000Coordinator, zone_number: int, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._zone_number = zone_number
        self._attr_unique_id = f"{entry.entry_id}_zone_{zone_number}"
        self._attr_name = f"Zone {zone_number}"
        self._attr_device_info = _device_info(entry)

    def _zone(self):
        if not self.coordinator.data:
            return None
        for z in self.coordinator.data.zones:
            if z.number == self._zone_number:
                return z
        return None

    @property
    def is_on(self) -> bool | None:
        z = self._zone()
        return z.is_open if z else None

    @property
    def extra_state_attributes(self) -> dict:
        z = self._zone()
        if z is None:
            return {}
        return {
            "violated": z.violated,
            "bypassed": z.bypassed,
            "tamper": z.tamper,
            "low_battery": z.low_battery,
        }


class Amt8000SirenSensor(CoordinatorEntity[Amt8000Coordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.SOUND

    def __init__(self, coordinator: Amt8000Coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_siren"
        self._attr_name = "Siren"
        self._attr_device_info = _device_info(entry)

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.siren_live
