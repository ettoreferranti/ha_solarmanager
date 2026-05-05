"""Sensor entities for Solar Manager v3."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SM_ID, DEVICE_SENSORS, DOMAIN, GATEWAY_SENSORS
from .coordinator import SolarManagerCoordinator


def _device_class_from_str(name: str | None) -> SensorDeviceClass | None:
    if name == "power":
        return SensorDeviceClass.POWER
    if name == "battery":
        return SensorDeviceClass.BATTERY
    if name == "temperature":
        return SensorDeviceClass.TEMPERATURE
    if name == "energy":
        return SensorDeviceClass.ENERGY
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for one config entry."""
    coordinator: SolarManagerCoordinator = hass.data[DOMAIN][entry.entry_id]
    sm_id = entry.data[CONF_SM_ID]

    entities: list[SensorEntity] = []

    # Gateway-level sensors
    for key, unit, dev_class, name, icon in GATEWAY_SENSORS:
        entities.append(
            SolarManagerGatewaySensor(
                coordinator=coordinator,
                sm_id=sm_id,
                field=key,
                unit=unit,
                device_class=_device_class_from_str(dev_class),
                name=name,
                icon=icon,
            )
        )

    # Per-device sensors: only create entities for fields present in the
    # very first stream payload, so we don't spam users with always-None
    # sensors for irrelevant fields (e.g. SOC for a non-battery inverter).
    devices_payload = (coordinator.data or {}).get("devices") or []
    for dev in devices_payload:
        dev_id = dev.get("_id")
        if not dev_id:
            continue
        meta = coordinator.devices_meta.get(dev_id, {})
        dev_name = meta.get("name") or f"Device {dev_id[-6:]}"
        dev_type = meta.get("type") or meta.get("device_type") or "Device"

        for key, unit, dev_class, label, icon in DEVICE_SENSORS:
            if key not in dev:
                continue
            entities.append(
                SolarManagerDeviceSensor(
                    coordinator=coordinator,
                    sm_id=sm_id,
                    device_id=dev_id,
                    device_name=dev_name,
                    device_type=dev_type,
                    field=key,
                    unit=unit,
                    device_class=_device_class_from_str(dev_class),
                    name=label,
                    icon=icon,
                )
            )

    async_add_entities(entities)


class _Base(CoordinatorEntity[SolarManagerCoordinator], SensorEntity):
    """Common base."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SolarManagerCoordinator) -> None:
        super().__init__(coordinator)


class SolarManagerGatewaySensor(_Base):
    """A sensor reading a top-level field of the stream payload."""

    def __init__(
        self,
        coordinator: SolarManagerCoordinator,
        sm_id: str,
        field: str,
        unit: str,
        device_class: SensorDeviceClass | None,
        name: str,
        icon: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._field = field
        self._sm_id = sm_id
        self._attr_name = name
        self._attr_unique_id = f"{sm_id}_gateway_{field}"
        self._attr_native_unit_of_measurement = unit or None
        self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.MEASUREMENT
        if icon:
            self._attr_icon = icon

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{sm_id}_gateway")},
            name=f"Solar Manager Gateway ({sm_id})",
            manufacturer="Solar Manager",
            model="Gateway",
        )

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        value = data.get(self._field)
        if value is None:
            return None
        # API returns numbers; just pass through.
        return value


class SolarManagerDeviceSensor(_Base):
    """A sensor reading a field from devices[] entries."""

    def __init__(
        self,
        coordinator: SolarManagerCoordinator,
        sm_id: str,
        device_id: str,
        device_name: str,
        device_type: str,
        field: str,
        unit: str,
        device_class: SensorDeviceClass | None,
        name: str,
        icon: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._field = field
        self._attr_name = name
        self._attr_unique_id = f"{sm_id}_dev_{device_id}_{field}"
        self._attr_native_unit_of_measurement = unit or None
        self._attr_device_class = device_class
        if device_class == SensorDeviceClass.ENERGY:
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif device_class is not None or unit in ("W", "%", "°C"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if icon:
            self._attr_icon = icon

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{sm_id}_dev_{device_id}")},
            name=device_name,
            manufacturer="Solar Manager",
            model=device_type,
            via_device=(DOMAIN, f"{sm_id}_gateway"),
        )

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        for dev in data.get("devices") or []:
            if dev.get("_id") == self._device_id:
                return dev.get(self._field)
        return None
