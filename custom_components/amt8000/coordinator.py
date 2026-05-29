"""DataUpdateCoordinator for AMT 8000."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import Amt8000Client, CannotConnect, InvalidAuth, PanelStatus
from .const import DOMAIN, EVENT_ALARM_TRIGGERED, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class Amt8000Coordinator(DataUpdateCoordinator[PanelStatus]):
    def __init__(self, hass: HomeAssistant, client: Amt8000Client) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        self._prev_siren = False

    async def _async_update_data(self) -> PanelStatus:
        try:
            status = await self.client.get_status()
        except InvalidAuth as exc:
            raise UpdateFailed(f"Authentication failed: {exc}") from exc
        except CannotConnect as exc:
            raise UpdateFailed(f"Cannot reach panel: {exc}") from exc

        # Rising edge on siren → fire HA event for automations
        if status.siren_live and not self._prev_siren:
            self.hass.bus.async_fire(
                EVENT_ALARM_TRIGGERED,
                {"partitions_firing": [p.index for p in status.partitions if p.firing]},
            )
        self._prev_siren = status.siren_live

        return status
