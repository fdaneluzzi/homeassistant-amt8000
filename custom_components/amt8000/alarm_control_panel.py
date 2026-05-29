"""Alarm control panel entities — one per user partition (groups 1-N)."""
from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import OpenZones
from .const import AGGREGATE_PARTITION_IDX, DOMAIN
from .coordinator import Amt8000Coordinator

import logging
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: Amt8000Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        Amt8000PartitionPanel(coordinator, p.index, entry)
        for p in coordinator.data.partitions
        if p.index != AGGREGATE_PARTITION_IDX
    )


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}")},
        name="Intelbras AMT 8000",
        manufacturer="Intelbras",
        model="AMT 8000",
    )


class Amt8000PartitionPanel(CoordinatorEntity[Amt8000Coordinator], AlarmControlPanelEntity):
    _attr_has_entity_name = True
    _attr_supported_features = AlarmControlPanelEntityFeature.ARM_AWAY
    _attr_code_arm_required = False
    _attr_code_disarm_required = False

    def __init__(
        self, coordinator: Amt8000Coordinator, partition_idx: int, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._partition_idx = partition_idx
        self._entry = entry
        # User-visible group number: skip the aggregate at index 0
        group_num = partition_idx  # idx 1 → "Group 1", idx 2 → "Group 2", etc.
        self._attr_unique_id = f"{entry.entry_id}_partition_{partition_idx}"
        self._attr_name = f"Group {group_num}"
        self._attr_device_info = _device_info(entry)

    def _partition(self):
        if not self.coordinator.data:
            return None
        for p in self.coordinator.data.partitions:
            if p.index == self._partition_idx:
                return p
        return None

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        p = self._partition()
        if p is None:
            return None
        if p.firing:
            return AlarmControlPanelState.TRIGGERED
        if p.armed:
            return AlarmControlPanelState.ARMED_AWAY
        return AlarmControlPanelState.DISARMED

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        try:
            await self.coordinator.client.arm_partition(self._partition_idx)
        except OpenZones:
            _LOGGER.warning("Group %d: arm blocked — open zones", self._partition_idx)
        await self.coordinator.async_request_refresh()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self.coordinator.client.disarm_partition(self._partition_idx)
        await self.coordinator.async_request_refresh()
