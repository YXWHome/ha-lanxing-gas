"""定时拉取兰星燃气账户数据的 DataUpdateCoordinator。"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AccountReading, LanxingGasApiClient, LanxingGasError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class LanxingGasCoordinator(DataUpdateCoordinator[list[AccountReading]]):
    """Coordinate polling of the Lanxing gas accounts."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.client = LanxingGasApiClient(hass, entry.data)
        interval = int(
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            or DEFAULT_SCAN_INTERVAL
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval),
        )

    async def _async_update_data(self) -> list[AccountReading]:
        try:
            return await self.client.async_fetch_my_accounts()
        except LanxingGasError as err:
            raise UpdateFailed(str(err)) from err
