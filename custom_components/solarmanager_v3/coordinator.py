"""DataUpdateCoordinator that polls whichever transport is configured."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN
from .transport import (
    SolarManagerApiError,
    SolarManagerAuthError,
    SolarManagerTransport,
)

_LOGGER = logging.getLogger(__name__)


class SolarManagerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the configured transport and stores the latest snapshot."""

    def __init__(
        self, hass: HomeAssistant, transport: SolarManagerTransport
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} snapshot",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.transport = transport
        # populated by __init__.py after first successful refresh
        self.devices_meta: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.transport.async_get_snapshot()
        except SolarManagerAuthError as err:
            raise UpdateFailed(f"Authentication failure: {err}") from err
        except SolarManagerApiError as err:
            raise UpdateFailed(f"API error: {err}") from err
        return data
