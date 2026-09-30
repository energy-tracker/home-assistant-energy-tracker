"""Config flow for the Energy Tracker integration."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow, FlowResult
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
STEP_RECONFIGURE_DATA_SCHEMA = vol.Schema({vol.Required(CONF_API_TOKEN): cv.string})


class EnergyTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Config flow handler for the Energy Tracker integration.

    This class manages the configuration and reconfiguration steps for the integration.
    """

    VERSION = 2

    @callback
    def _async_abort_if_token_configured(self, token: str) -> None:
        """Match normalized tokens, including entries created before normalization."""
        for entry in self._async_current_entries(include_ignore=False):
            if entry.entry_id == self.context.get("entry_id"):
                continue
            stored_token = entry.data.get(CONF_API_TOKEN)
            if isinstance(stored_token, str) and stored_token.strip() == token:
                raise AbortFlow("already_configured")

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            token = user_input[CONF_API_TOKEN].strip()
            if not name:
                errors[CONF_NAME] = "required"
            if not token:
                errors[CONF_API_TOKEN] = "required"
            if not errors:
                self._async_abort_if_token_configured(token)
                await self.async_set_unique_id(token_unique_id(token))
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={CONF_API_TOKEN: token},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle reconfiguration of the integration."""
        entry = self._get_reconfigure_entry()

        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            if not token:
                errors[CONF_API_TOKEN] = "required"
            else:
                self._async_abort_if_token_configured(token)
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
            data_schema=STEP_RECONFIGURE_DATA_SCHEMA,
            errors=errors,
        )
