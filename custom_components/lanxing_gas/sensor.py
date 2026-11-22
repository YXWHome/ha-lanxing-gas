"""宁夏兰星天然气传感器实体（每个账户一组）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AccountReading
from .const import DOMAIN
from .coordinator import LanxingGasCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class LanxingGasSensorDescription(SensorEntityDescription):
    """Description with an extractor for one account value."""

    value_fn: Callable[[AccountReading], Any]


SENSORS: tuple[LanxingGasSensorDescription, ...] = (
    LanxingGasSensorDescription(
        key="balance",
        translation_key="balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:cash",
        value_fn=lambda r: r.balance,
    ),
    LanxingGasSensorDescription(
        key="estimated_balance",
        translation_key="estimated_balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:cash-check",
        value_fn=lambda r: r.estimated_balance,
    ),
    LanxingGasSensorDescription(
        key="remaining_gas",
        translation_key="remaining_gas",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:fire",
        value_fn=lambda r: r.last_gas,
    ),
    LanxingGasSensorDescription(
        key="total_gas",
        translation_key="total_gas",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        icon="mdi:fire",
        value_fn=lambda r: r.total_gas,
    ),
    LanxingGasSensorDescription(
        key="last_settlement",
        translation_key="last_settlement",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
        value_fn=lambda r: r.last_settled,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lanxing gas sensors from a config entry."""
    coordinator: LanxingGasCoordinator = entry.runtime_data
    entities: list[LanxingGasSensor] = []
    for index, reading in enumerate(coordinator.data or []):
        for description in SENSORS:
            entities.append(LanxingGasSensor(coordinator, reading.cust_id, index, description))
    async_add_entities(entities, update_before_add=False)


class LanxingGasSensor(CoordinatorEntity[LanxingGasCoordinator], SensorEntity):
    """A sensor for one value of one gas account."""

    _attr_has_entity_name = True
    entity_description: LanxingGasSensorDescription

    def __init__(
        self,
        coordinator: LanxingGasCoordinator,
        cust_id: str,
        index: int,
        description: LanxingGasSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._cust_id = cust_id
        self._index = index
        self._attr_unique_id = f"{cust_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cust_id)},
            name=f"兰星燃气 {cust_id}",
            manufacturer="宁夏兰星天然气开发有限公司",
            model="远传表-NB",
        )

    @property
    def native_value(self):
        """Return the value from the latest coordinator reading."""
        data = self.coordinator.data or []
        if self._index >= len(data):
            return None
        return self.entity_description.value_fn(data[self._index])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose account identity as attributes."""
        data = self.coordinator.data or []
        if self._index >= len(data):
            return {}
        reading: AccountReading = data[self._index]
        attrs: dict[str, Any] = {
            "cust_id": reading.cust_id,
            "用户编号": reading.cust_code,
            "户主": reading.cust_name,
            "地址": reading.address,
            "表号": reading.meter_code,
            "电话": reading.phone,
        }
        if reading.meter_type:
            attrs["表类型"] = reading.meter_type
        if reading.last_buy_num is not None:
            attrs["最近购气量"] = reading.last_buy_num
        if reading.last_buy_date:
            attrs["最近购气日期"] = reading.last_buy_date
        if reading.remote_buy_num is not None:
            attrs["远传累计购气"] = reading.remote_buy_num
        # Stair-step pricing info (used for the estimated balance)
        if reading.current_tier:
            attrs["当前阶梯"] = reading.current_tier
        if reading.last_gas is not None and reading.total_gas is not None:
            attrs["余额推算说明"] = (
                f"剩余 {reading.last_gas} 方 × 当前阶梯单价 = {reading.estimated_balance} 元"
                "（接口余额恒为0，此为估算）"
            )
        return attrs
