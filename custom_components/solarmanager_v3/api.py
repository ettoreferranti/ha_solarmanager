"""Lightweight async client for the Solar Manager External API (read-only)."""
from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp
import async_timeout

from .const import (
    API_BASE,
    ENDPOINT_INFO_SENSORS,
    ENDPOINT_LOGIN,
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


class SolarManagerClient:
    """Minimal read-only client.

    Owns an access token + refresh token and renews them transparently.
    The access-token lifetime returned by Solar Manager is not fixed in the
    public docs, so we treat any 401 as "refresh and retry once".
    """

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
        self._access_token_expires_at: float = 0.0  # epoch seconds

    # ---- public surface ---------------------------------------------------

    async def async_test_credentials(self) -> None:
        """Try logging in once. Raises on failure."""
        await self._login()

    async def async_get_stream(self) -> dict[str, Any]:
        """Return the latest gateway + per-device stream snapshot."""
        return await self._get_with_auth(ENDPOINT_STREAM.format(sm_id=self._sm_id))

    async def async_get_sensors_info(self) -> list[dict[str, Any]]:
        """Return the device list (used for naming on first setup)."""
        result = await self._get_with_auth(
            ENDPOINT_INFO_SENSORS.format(sm_id=self._sm_id)
        )
        # The endpoint returns a list directly per the swagger spec.
        if isinstance(result, list):
            return result
        return []

    # ---- internals --------------------------------------------------------

    async def _login(self) -> None:
        url = f"{API_BASE}{ENDPOINT_LOGIN}"
        payload = {"email": self._email, "password": self._password}
        try:
            async with async_timeout.timeout(REQUEST_TIMEOUT_SECONDS):
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
            async with async_timeout.timeout(REQUEST_TIMEOUT_SECONDS):
                async with self._session.post(url, json=payload) as resp:
                    if resp.status in (401, 403):
                        # refresh token rejected -> full re-login
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
        # Field names in the response: the swagger labels them generically as
        # Model68 / Model70. Common JWT-issuer responses use either
        # accessToken/refreshToken or access_token/refresh_token. Accept both.
        access = (
            data.get("accessToken")
            or data.get("access_token")
            or data.get("token")
        )
        refresh = (
            data.get("refreshToken")
            or data.get("refresh_token")
        )
        # Lifetime hint, if any
        ttl = (
            data.get("expiresIn")
            or data.get("expires_in")
            or 3600  # safe default
        )

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
        _LOGGER.debug(
            "Stored tokens; access valid for ~%ss", ttl_int
        )

    async def _ensure_token(self) -> None:
        if self._access_token is None:
            await self._login()
            return
        if time.time() >= self._access_token_expires_at:
            await self._refresh()

    async def _get_with_auth(self, path: str) -> Any:
        """GET path with bearer auth; on 401 refresh once and retry."""
        await self._ensure_token()
        url = f"{API_BASE}{path}"

        for attempt in (1, 2):
            headers = {"Authorization": f"Bearer {self._access_token}"}
            try:
                async with async_timeout.timeout(REQUEST_TIMEOUT_SECONDS):
                    async with self._session.get(url, headers=headers) as resp:
                        if resp.status == 401 and attempt == 1:
                            _LOGGER.debug("401 on %s, refreshing token", path)
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

        # Shouldn't be reachable
        raise SolarManagerApiError(f"GET {path} failed after retry")
