"""Config and options flow for Solar Manager v3."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_SM_ID,
    CONF_TRANSPORT,
    CONF_VERIFY_SSL,
    DOMAIN,
    TRANSPORT_CLOUD,
    TRANSPORT_LOCAL,
)
from .transport import (
    CloudTransport,
    LocalTransport,
    SolarManagerApiError,
    SolarManagerAuthError,
)

_LOGGER = logging.getLogger(__name__)


CLOUD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_SM_ID): str,
    }
)

LOCAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_SM_ID, default=""): str,
        vol.Optional(CONF_VERIFY_SSL, default=False): bool,
    }
)


class SolarManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Initial setup flow with a transport choice."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        return self.async_show_menu(
            step_id="user",
            menu_options=[TRANSPORT_CLOUD, TRANSPORT_LOCAL],
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            sm_id = user_input[CONF_SM_ID].strip()

            await self.async_set_unique_id(sm_id)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = CloudTransport(session, email, password, sm_id)

            try:
                await client.async_test()
            except SolarManagerAuthError:
                errors["base"] = "invalid_auth"
            except SolarManagerApiError as err:
                _LOGGER.warning("API error during cloud config: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during cloud config")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Solar Manager Cloud ({sm_id})",
                    data={
                        CONF_TRANSPORT: TRANSPORT_CLOUD,
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_SM_ID: sm_id,
                    },
                )

        return self.async_show_form(
            step_id=TRANSPORT_CLOUD,
            data_schema=CLOUD_SCHEMA,
            errors=errors,
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            api_key = user_input[CONF_API_KEY].strip()
            sm_id = (user_input.get(CONF_SM_ID) or "").strip() or host
            verify_ssl = bool(user_input.get(CONF_VERIFY_SSL, False))

            await self.async_set_unique_id(f"local:{sm_id}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = LocalTransport(session, host, api_key, verify_ssl=verify_ssl)

            try:
                await client.async_test()
            except SolarManagerAuthError:
                errors["base"] = "invalid_auth"
            except SolarManagerApiError as err:
                _LOGGER.warning("API error during local config: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during local config")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Solar Manager Local ({host})",
                    data={
                        CONF_TRANSPORT: TRANSPORT_LOCAL,
                        CONF_HOST: host,
                        CONF_API_KEY: api_key,
                        CONF_SM_ID: sm_id,
                        CONF_VERIFY_SSL: verify_ssl,
                    },
                )

        return self.async_show_form(
            step_id=TRANSPORT_LOCAL,
            data_schema=LOCAL_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SolarManagerOptionsFlow:
        return SolarManagerOptionsFlow(config_entry)


class SolarManagerOptionsFlow(config_entries.OptionsFlow):
    """Lets the user swap transport (and update credentials) post-setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[TRANSPORT_CLOUD, TRANSPORT_LOCAL],
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self.config_entry.data

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            sm_id = user_input[CONF_SM_ID].strip()

            session = async_get_clientsession(self.hass)
            client = CloudTransport(session, email, password, sm_id)

            try:
                await client.async_test()
            except SolarManagerAuthError:
                errors["base"] = "invalid_auth"
            except SolarManagerApiError as err:
                _LOGGER.warning("API error during cloud options: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during cloud options")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=f"Solar Manager Cloud ({sm_id})",
                    data={
                        CONF_TRANSPORT: TRANSPORT_CLOUD,
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_SM_ID: sm_id,
                    },
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_EMAIL,
                    default=current.get(CONF_EMAIL, ""),
                ): str,
                vol.Required(
                    CONF_PASSWORD,
                    default=current.get(CONF_PASSWORD, ""),
                ): str,
                vol.Required(
                    CONF_SM_ID,
                    default=current.get(CONF_SM_ID, ""),
                ): str,
            }
        )
        return self.async_show_form(
            step_id=TRANSPORT_CLOUD,
            data_schema=schema,
            errors=errors,
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        current = self.config_entry.data

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            api_key = user_input[CONF_API_KEY].strip()
            sm_id = (user_input.get(CONF_SM_ID) or "").strip() or host
            verify_ssl = bool(user_input.get(CONF_VERIFY_SSL, False))

            session = async_get_clientsession(self.hass)
            client = LocalTransport(session, host, api_key, verify_ssl=verify_ssl)

            try:
                await client.async_test()
            except SolarManagerAuthError:
                errors["base"] = "invalid_auth"
            except SolarManagerApiError as err:
                _LOGGER.warning("API error during local options: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during local options")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=f"Solar Manager Local ({host})",
                    data={
                        CONF_TRANSPORT: TRANSPORT_LOCAL,
                        CONF_HOST: host,
                        CONF_API_KEY: api_key,
                        CONF_SM_ID: sm_id,
                        CONF_VERIFY_SSL: verify_ssl,
                    },
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=current.get(CONF_HOST, ""),
                ): str,
                vol.Required(
                    CONF_API_KEY,
                    default=current.get(CONF_API_KEY, ""),
                ): str,
                vol.Optional(
                    CONF_SM_ID,
                    default=current.get(CONF_SM_ID, ""),
                ): str,
                vol.Optional(
                    CONF_VERIFY_SSL,
                    default=current.get(CONF_VERIFY_SSL, False),
                ): bool,
            }
        )
        return self.async_show_form(
            step_id=TRANSPORT_LOCAL,
            data_schema=schema,
            errors=errors,
        )
