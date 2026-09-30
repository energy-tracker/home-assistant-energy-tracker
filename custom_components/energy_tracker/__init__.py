"""Initialization for the Energy Tracker integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .api import EnergyTrackerApi
from .const import CONF_API_TOKEN, DOMAIN, SERVICE_SEND_METER_READING
from .identity import token_unique_id

type EnergyTrackerConfigEntry = ConfigEntry[EnergyTrackerApi]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

LOGGER = logging.getLogger(__name__)

SERVICE_SEND_METER_READING_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("source_entity_id"): cv.entity_id,
        vol.Required("entry_id"): cv.string,
        vol.Optional("allow_rounding", default=True): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the action independently of loaded accounts."""

    async def handle_send_meter_reading(call: ServiceCall) -> None:
        await async_handle_send_meter_reading(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_METER_READING,
        handle_send_meter_reading,
        schema=SERVICE_SEND_METER_READING_SCHEMA,
    )
    return True


def _select_api_for_service(hass: HomeAssistant, call: ServiceCall) -> EnergyTrackerApi:
    """Select only a loaded Energy Tracker account for a service call."""
    entry_id = call.data.get("entry_id")
    entry: EnergyTrackerConfigEntry | None = (
        hass.config_entries.async_get_entry(entry_id) if entry_id else None
    )
    if (
        entry is None
        or entry.domain != DOMAIN
        or entry.state is not ConfigEntryState.LOADED
        or not entry.data.get(CONF_API_TOKEN)
    ):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="account_unavailable",
        )
    return entry.runtime_data


async def async_handle_send_meter_reading(
    hass: HomeAssistant,
    call: ServiceCall,
) -> None:
    """Handle the send_meter_reading service.

    Reads the current value from a Home Assistant entity and sends it
    as a meter reading to the Energy Tracker backend.

    Raises:
        HomeAssistantError: If the meter reading could not be sent.
    """
    api = _select_api_for_service(hass, call)
    device_id: str = call.data["device_id"].strip()
    source_entity_id: str = call.data["source_entity_id"]
    allow_rounding: bool = call.data.get("allow_rounding", True)

    state_obj: State | None = hass.states.get(source_entity_id)
    if state_obj is None:
        LOGGER.error("Source entity %s not found", source_entity_id)
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="entity_not_found",
            translation_placeholders={"entity_id": source_entity_id},
        )

    raw_state = state_obj.state
    if raw_state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        LOGGER.warning("Source entity %s is %s", source_entity_id, raw_state)
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="entity_unavailable",
            translation_placeholders={
                "entity_id": source_entity_id,
                "state": raw_state,
            },
        )

    try:
        value = float(raw_state)
    except (TypeError, ValueError) as err:
        LOGGER.error(
            "Could not convert state '%s' of %s to number", raw_state, source_entity_id
        )
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="invalid_number",
            translation_placeholders={
                "entity_id": source_entity_id,
                "state": raw_state,
            },
        ) from err

    if state_obj.last_updated is None:
        LOGGER.error("Source entity %s has no last_updated timestamp", source_entity_id)
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="missing_timestamp",
            translation_placeholders={"entity_id": source_entity_id},
        )
    timestamp = state_obj.last_updated

    await api.send_meter_reading(
        source_entity_id=source_entity_id,
        device_id=device_id,
        value=value,
        timestamp=timestamp,
        allow_rounding=allow_rounding,
    )


async def async_migrate_entry(
    hass: HomeAssistant, entry: EnergyTrackerConfigEntry
) -> bool:
    """Replace legacy plaintext token IDs without changing account references."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry,
            unique_id=token_unique_id(entry.data[CONF_API_TOKEN]),
            version=2,
            minor_version=1,
        )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: EnergyTrackerConfigEntry
) -> bool:
    """Create one API client for the lifetime of this loaded account."""
    api = entry.runtime_data = EnergyTrackerApi(token=entry.data[CONF_API_TOKEN])

    async def close_on_stop(event: Event) -> None:
        await api.async_close()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, close_on_stop)
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: EnergyTrackerConfigEntry
) -> bool:
    """Close this account's client while retaining the integration action."""
    await entry.runtime_data.async_close()
    return True
