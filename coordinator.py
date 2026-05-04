"""DataUpdateCoordinator that polls the v3 stream endpoint."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import SolarManagerApiError, SolarManagerAuthError, SolarManagerClient
from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SolarManagerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls /v3/users/{smId}/data/stream and stores the latest payload."""

    def __init__(self, hass: HomeAssistant, client: SolarManagerClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} stream",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        # populated by __init__.py after first successful refresh
        self.devices_meta: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.client.async_get_stream()
        except SolarManagerAuthError as err:
            raise UpdateFailed(f"Authentication failure: {err}") from err
        except SolarManagerApiError as err:
            raise UpdateFailed(f"API error: {err}") from err
        return data
