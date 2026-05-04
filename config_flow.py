"""Config flow for Solar Manager v3."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SolarManagerApiError, SolarManagerAuthError, SolarManagerClient
from .const import CONF_SM_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_SM_ID): str,
    }
)


class SolarManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
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
            client = SolarManagerClient(session, email, password, sm_id)

            try:
                await client.async_test_credentials()
            except SolarManagerAuthError:
                errors["base"] = "invalid_auth"
            except SolarManagerApiError as err:
                _LOGGER.warning("API error during config: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during config")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Solar Manager ({sm_id})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_SM_ID: sm_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
