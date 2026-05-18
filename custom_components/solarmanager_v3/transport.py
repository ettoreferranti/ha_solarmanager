"""Transport layer for the Solar Manager integration.

Two interchangeable transports speak to either the cloud REST API or the
gateway's local HTTPS API. Both return the same normalized snapshot shape
so the coordinator and sensor platform don't need to care which is in use.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol

import aiohttp

from .const import (
    API_BASE,
    ENDPOINT_INFO_SENSORS,
    ENDPOINT_LOGIN,
    ENDPOINT_LOCAL_POINT,
    ENDPOINT_REFRESH,
    ENDPOINT_STREAM,
    REQUEST_TIMEOUT_SECONDS,
    TOKEN_REFRESH_LEEWAY_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class SolarManagerAuthError(Exception):
    """Raised when login or refresh fails."""


class SolarManagerApiError(Exception):
    """Raised on non-auth API errors."""


class SolarManagerTransport(Protocol):
    """Interface implemented by both Cloud and Local transports."""

    async def async_test(self) -> None: ...
    async def async_get_snapshot(self) -> dict[str, Any]: ...
    async def async_get_devices_meta(self) -> list[dict[str, Any]]: ...


# ---- Cloud ---------------------------------------------------------------


class CloudTransport:
    """Talks to https://cloud.solar-manager.ch with email/password + JWT."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        sm_id: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._sm_id = sm_id

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._access_token_expires_at: float = 0.0

    async def async_test(self) -> None:
        await self._login()

    async def async_get_snapshot(self) -> dict[str, Any]:
        return await self._get_with_auth(ENDPOINT_STREAM.format(sm_id=self._sm_id))

    async def async_get_devices_meta(self) -> list[dict[str, Any]]:
        result = await self._get_with_auth(
            ENDPOINT_INFO_SENSORS.format(sm_id=self._sm_id)
        )
        if isinstance(result, list):
            return result
        return []

    async def _login(self) -> None:
        url = f"{API_BASE}{ENDPOINT_LOGIN}"
        payload = {"email": self._email, "password": self._password}
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                async with self._session.post(url, json=payload) as resp:
                    if resp.status in (401, 403):
                        raise SolarManagerAuthError(
                            f"Login rejected ({resp.status})"
                        )
                    if resp.status >= 400:
                        text = await resp.text()
                        raise SolarManagerApiError(
                            f"Login HTTP {resp.status}: {text[:200]}"
                        )
                    data = await resp.json()
        except aiohttp.ClientError as err:
            raise SolarManagerApiError(f"Login network error: {err}") from err

        self._store_tokens(data)

    async def _refresh(self) -> None:
        if not self._refresh_token:
            await self._login()
            return

        url = f"{API_BASE}{ENDPOINT_REFRESH}"
        payload = {"refreshToken": self._refresh_token}
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                async with self._session.post(url, json=payload) as resp:
                    if resp.status in (401, 403):
                        _LOGGER.debug("Refresh rejected, falling back to login")
                        await self._login()
                        return
                    if resp.status >= 400:
                        text = await resp.text()
                        raise SolarManagerApiError(
                            f"Refresh HTTP {resp.status}: {text[:200]}"
                        )
                    data = await resp.json()
        except aiohttp.ClientError as err:
            raise SolarManagerApiError(f"Refresh network error: {err}") from err

        self._store_tokens(data)

    def _store_tokens(self, data: dict[str, Any]) -> None:
        access = (
            data.get("accessToken")
            or data.get("access_token")
            or data.get("token")
        )
        refresh = data.get("refreshToken") or data.get("refresh_token")
        ttl = data.get("expiresIn") or data.get("expires_in") or 3600

        if not access:
            raise SolarManagerAuthError(
                f"Login response missing access token: keys={list(data)}"
            )

        self._access_token = access
        if refresh:
            self._refresh_token = refresh
        try:
            ttl_int = int(ttl)
        except (TypeError, ValueError):
            ttl_int = 3600
        self._access_token_expires_at = time.time() + max(
            ttl_int - TOKEN_REFRESH_LEEWAY_SECONDS, 30
        )

    async def _ensure_token(self) -> None:
        if self._access_token is None:
            await self._login()
            return
        if time.time() >= self._access_token_expires_at:
            await self._refresh()

    async def _get_with_auth(self, path: str) -> Any:
        await self._ensure_token()
        url = f"{API_BASE}{path}"

        for attempt in (1, 2):
            headers = {"Authorization": f"Bearer {self._access_token}"}
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                    async with self._session.get(url, headers=headers) as resp:
                        if resp.status == 401 and attempt == 1:
                            await self._refresh()
                            continue
                        if resp.status >= 400:
                            text = await resp.text()
                            raise SolarManagerApiError(
                                f"GET {path} HTTP {resp.status}: {text[:200]}"
                            )
                        return await resp.json()
            except aiohttp.ClientError as err:
                raise SolarManagerApiError(
                    f"Network error on {path}: {err}"
                ) from err

        raise SolarManagerApiError(f"GET {path} failed after retry")


# ---- Local ---------------------------------------------------------------


class LocalTransport:
    """Talks to the gateway directly over HTTPS using a static API key."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        api_key: str,
        verify_ssl: bool = False,
    ) -> None:
        self._session = session
        self._base_url = _normalize_host(host)
        self._api_key = api_key
        self._verify_ssl = verify_ssl
        # Cached once the grid-meter device is identified by matching its
        # cumulative iWh/eWh against the gateway totals. Survives transient
        # poll cycles where the totals are near-zero and ambiguous.
        self._grid_meter_id: str | None = None

    async def async_test(self) -> None:
        await self._get_point()

    async def async_get_snapshot(self) -> dict[str, Any]:
        raw = await self._get_point()
        return self._normalize(raw)

    async def async_get_devices_meta(self) -> list[dict[str, Any]]:
        # Local API has no equivalent of /info/sensors; device names/types
        # are unavailable in this mode.
        return []

    async def _get_point(self) -> dict[str, Any]:
        url = f"{self._base_url}{ENDPOINT_LOCAL_POINT}"
        headers = {
            "Accept": "application/json",
            "X-API-Key": self._api_key,
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                async with self._session.get(
                    url, headers=headers, ssl=self._verify_ssl
                ) as resp:
                    if resp.status in (401, 403):
                        raise SolarManagerAuthError(
                            f"Local API rejected key ({resp.status})"
                        )
                    if resp.status >= 400:
                        text = await resp.text()
                        raise SolarManagerApiError(
                            f"GET /v2/point HTTP {resp.status}: {text[:200]}"
                        )
                    data = await resp.json()
        except aiohttp.ClientError as err:
            raise SolarManagerApiError(
                f"Network error on local /v2/point: {err}"
            ) from err

        if not isinstance(data, dict):
            raise SolarManagerApiError("Local /v2/point did not return a JSON object")
        return data

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Reshape the local /v2/point payload to match what sensor.py expects.

        Two adjustments:
        1. Per-device energy keys: local emits `iWh`/`eWh`, cloud emits
           `iWhTotal`/`eWhTotal`. We alias rather than rename so
           debugging-by-eye stays easy.
        2. Synthesize gateway `iW`/`eW` (instantaneous grid import/export
           power) from the grid meter device's signed `power`. The local
           API doesn't expose these as gateway fields, but the grid meter
           is identifiable as the device whose cumulative `iWh`/`eWh` is
           closest to the gateway-level totals. Sign convention: negative
           power on the meter = export, positive = import (verified from
           real payloads).
        """
        devices = raw.get("devices") or []
        normalized_devices: list[dict[str, Any]] = []
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            new = dict(dev)
            if "iWh" in new and "iWhTotal" not in new:
                new["iWhTotal"] = new["iWh"]
            if "eWh" in new and "eWhTotal" not in new:
                new["eWhTotal"] = new["eWh"]
            normalized_devices.append(new)

        out = dict(raw)
        out["devices"] = normalized_devices

        meter = self._identify_grid_meter(raw, normalized_devices)
        if meter is None and self._grid_meter_id is not None:
            for dev in normalized_devices:
                if dev.get("_id") == self._grid_meter_id:
                    meter = dev
                    break
        if meter is not None:
            self._grid_meter_id = meter.get("_id") or self._grid_meter_id
            try:
                power = float(meter.get("power", 0) or 0)
            except (TypeError, ValueError):
                power = 0.0
            out["iW"] = max(power, 0.0)
            out["eW"] = max(-power, 0.0)

        return out

    def _identify_grid_meter(
        self, raw: dict[str, Any], devices: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Pick the device whose (iWh, eWh) is closest to the gateway's.

        Returns ``None`` if multiple devices tie for closest (ambiguous,
        e.g. right after a daily reset where everything is at zero), or
        if even the closest is implausibly far away.
        """
        g_iWh = raw.get("iWh")
        g_eWh = raw.get("eWh")
        if g_iWh is None or g_eWh is None:
            return None
        try:
            g_iWh_f = float(g_iWh)
            g_eWh_f = float(g_eWh)
        except (TypeError, ValueError):
            return None

        best: dict[str, Any] | None = None
        best_diff: float | None = None
        ties = 0
        for dev in devices:
            d_iWh = dev.get("iWh")
            d_eWh = dev.get("eWh")
            if d_iWh is None or d_eWh is None:
                continue
            try:
                diff = abs(float(d_iWh) - g_iWh_f) + abs(float(d_eWh) - g_eWh_f)
            except (TypeError, ValueError):
                continue
            if best_diff is None or diff < best_diff:
                best = dev
                best_diff = diff
                ties = 1
            elif diff == best_diff:
                ties += 1

        # Plausibility cap: even the closest match must be within a few Wh.
        # Cumulative energies grow monotonically, so the grid meter and the
        # gateway should agree very tightly; anything farther suggests no
        # grid meter is present in this payload.
        max_acceptable_diff = 5.0  # Wh
        if (
            best is not None
            and ties == 1
            and best_diff is not None
            and best_diff < max_acceptable_diff
        ):
            return best
        return None


def _normalize_host(host: str) -> str:
    """Accept '192.168.1.10', 'https://192.168.1.10', or with trailing /."""
    host = host.strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host
