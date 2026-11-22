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
            readings = await self.client.async_fetch_my_accounts()
            # Live volume from the service-account balance page (no OpenID needed)
            try:
                gateway = await self.client.async_gateway_realtime()
            except Exception as err:  # noqa: BLE001 - gateway is best-effort
                _LOGGER.debug("网关实时数据跳过: %s", err)
                gateway = {}
            by_meter = gateway.get("by_meter") or {}
            for reading in readings:
                live = by_meter.get(reading.meter_code or "") or by_meter.get(
                    reading.cust_code or ""
                )
                if not live:
                    continue
                if live.get("last_gas") is not None:
                    reading.last_gas = live["last_gas"]
                if live.get("total_gas") is not None:
                    reading.total_gas = live["total_gas"]
                if live.get("last_settled") is not None:
                    reading.last_settled = live["last_settled"]
                if gateway.get("openid") and not reading.raw.get("gateway_openid"):
                    reading.raw["gateway_openid"] = gateway["openid"]
            return readings
        except LanxingGasError as err:
            raise UpdateFailed(str(err)) from err
