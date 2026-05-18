"""Solar Manager v3 (read-only) integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_SM_ID,
    CONF_TRANSPORT,
    CONF_VERIFY_SSL,
    DEFAULT_TRANSPORT,
    DOMAIN,
    TRANSPORT_LOCAL,
)
from .coordinator import SolarManagerCoordinator
from .transport import (
    CloudTransport,
    LocalTransport,
    SolarManagerApiError,
    SolarManagerAuthError,
    SolarManagerTransport,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def _build_transport(hass: HomeAssistant, entry: ConfigEntry) -> SolarManagerTransport:
    session = async_get_clientsession(hass)
    transport_kind = entry.data.get(CONF_TRANSPORT, DEFAULT_TRANSPORT)
    if transport_kind == TRANSPORT_LOCAL:
        return LocalTransport(
            session=session,
            host=entry.data[CONF_HOST],
            api_key=entry.data[CONF_API_KEY],
            verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
        )
    return CloudTransport(
        session=session,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        sm_id=entry.data[CONF_SM_ID],
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Manager from a config entry."""
    transport = _build_transport(hass, entry)
    coordinator = SolarManagerCoordinator(hass, transport)

    # Device metadata for friendly names — only the cloud transport has this.
    try:
        meta = await transport.async_get_devices_meta()
        coordinator.devices_meta = {
            d["_id"]: d for d in meta if isinstance(d, dict) and "_id" in d
        }
    except SolarManagerAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SolarManagerApiError as err:
        _LOGGER.warning("Could not fetch device metadata on startup: %s", err)
        coordinator.devices_meta = {}

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Initial fetch failed: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its data is updated by the options flow."""
    await hass.config_entries.async_reload(entry.entry_id)
