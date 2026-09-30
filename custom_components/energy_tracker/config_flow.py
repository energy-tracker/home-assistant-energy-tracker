"""Config flow for the Energy Tracker integration."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import CONF_API_TOKEN, DOMAIN
from .identity import token_unique_id

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_API_TOKEN): cv.string,
    }
)


class EnergyTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Config flow handler for the Energy Tracker integration.

    This class manages the configuration and reconfiguration steps for the integration.
    """

    VERSION = 2

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_API_TOKEN: user_input[CONF_API_TOKEN]}
            )
            await self.async_set_unique_id(token_unique_id(user_input[CONF_API_TOKEN]))
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={CONF_API_TOKEN: user_input[CONF_API_TOKEN]},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle reconfiguration of the integration."""
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            token = user_input[CONF_API_TOKEN]
            self._async_abort_entries_match({CONF_API_TOKEN: token})
            unique_id = token_unique_id(token)
            if unique_id != entry.unique_id:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

            return self.async_update_reload_and_abort(
                entry,
                unique_id=unique_id,
                data={CONF_API_TOKEN: token},
                reason="reconfigure_successful",
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_TOKEN): cv.string,
                }
            ),
        )
