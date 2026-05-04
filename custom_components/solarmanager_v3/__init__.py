"""Solar Manager v3 (read-only) integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SolarManagerApiError, SolarManagerAuthError, SolarManagerClient
from .const import CONF_SM_ID, DOMAIN
from .coordinator import SolarManagerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Manager from a config entry."""
    session = async_get_clientsession(hass)
    client = SolarManagerClient(
        session=session,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        sm_id=entry.data[CONF_SM_ID],
    )

    coordinator = SolarManagerCoordinator(hass, client)

    # Fetch device metadata once for nice names; non-fatal if it fails.
    try:
        sensors_info = await client.async_get_sensors_info()
        coordinator.devices_meta = {
            d["_id"]: d
            for d in sensors_info
            if isinstance(d, dict) and "_id" in d
        }
    except SolarManagerAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SolarManagerApiError as err:
        _LOGGER.warning("Could not fetch sensors info on startup: %s", err)
        coordinator.devices_meta = {}

    # First refresh; will raise ConfigEntryNotReady on transient failure.
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Initial fetch failed: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
