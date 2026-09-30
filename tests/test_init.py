"""Tests for the Energy Tracker __init__ module."""

from __future__ import annotations

import asyncio
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from energy_tracker_api import EnergyTrackerClient
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HassJob, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_tracker import (
    async_handle_send_meter_reading,
    async_setup,
)
from custom_components.energy_tracker.api import EnergyTrackerApi
from custom_components.energy_tracker.const import (
    CONF_API_TOKEN,
    DOMAIN,
    SERVICE_SEND_METER_READING,
)


def create_service_call(
    hass: HomeAssistant,
    domain: str,
    service: str,
    data: dict,
) -> ServiceCall:
    """Create a ServiceCall instance for testing."""
    return ServiceCall(hass, domain, service, data=data)


@pytest.fixture
def sdk_requests(aioclient_mock):
    """Mock HTTP requests while retaining real SDK-owned sessions."""
    with patch("aiohttp.ClientSession._request", new=aioclient_mock.match_request):
        yield aioclient_mock


@pytest.fixture
async def loaded_entry(hass):
    """Set up an account through HA's normal lifecycle."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_TOKEN: "old-token"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    hass.states.async_set("sensor.meter", "123.45")
    return entry


@pytest.fixture
def reading_data(loaded_entry):
    """Provide service data for the loaded account."""
    return {
        "entry_id": loaded_entry.entry_id,
        "device_id": "device-123",
        "source_entity_id": "sensor.meter",
    }


@pytest.fixture
async def open_session(hass, loaded_entry, reading_data, sdk_requests):
    """Open a real SDK session using a mocked HTTP response."""
    sdk_requests.post(
        "https://public-api.energy-tracker.best-ios-apps.de/v1/devices/standard/device-123/meter-readings",
        status=201,
    )
    await hass.services.async_call(
        DOMAIN, SERVICE_SEND_METER_READING, reading_data, blocking=True
    )
    return loaded_entry.runtime_data._client._session


@pytest.fixture
async def delayed_api_server(aiohttp_server, monkeypatch):
    """Hold local POST responses until the test releases them."""
    received = asyncio.Queue()
    release = asyncio.Event()

    async def handle(request):
        received.put_nowait(await request.json())
        await release.wait()
        return web.Response(status=201)

    app = web.Application()
    app.router.add_post("/v1/devices/standard/device-123/meter-readings", handle)
    server = await aiohttp_server(app)
    monkeypatch.setattr(
        "custom_components.energy_tracker.api.EnergyTrackerClient",
        partial(EnergyTrackerClient, base_url=str(server.make_url("/"))),
    )
    try:
        yield received, release
    finally:
        release.set()


@pytest.fixture
async def local_entry(hass, delayed_api_server):
    """Set up an account after redirecting the SDK to the local server."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_TOKEN: "test-token"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    hass.states.async_set("sensor.meter", "123.45")
    return entry


@pytest.mark.enable_socket
async def test_reload_waits_for_in_flight_writes(
    hass, local_entry, delayed_api_server, start_task, monkeypatch
):
    """Do not disconnect accepted POSTs before receiving their responses."""
    # Arrange
    received, release = delayed_api_server
    entry = local_entry
    api = entry.runtime_data
    closing = asyncio.Event()
    data = {
        "entry_id": entry.entry_id,
        "device_id": "device-123",
        "source_entity_id": "sensor.meter",
    }
    calls = [
        start_task(
            hass.services.async_call(
                DOMAIN, SERVICE_SEND_METER_READING, data, blocking=True
            )
        )
        for _ in range(2)
    ]
    await asyncio.wait_for(received.get(), timeout=5)
    await asyncio.wait_for(received.get(), timeout=5)
    session = api._client._session
    close = api.async_close

    async def close_client():
        closing.set()
        await close()

    monkeypatch.setattr(api, "async_close", close_client)

    # Act
    reload_task = start_task(hass.config_entries.async_reload(entry.entry_id))
    await asyncio.wait_for(closing.wait(), timeout=5)
    reload_pending = not reload_task.done()
    session_open_during_reload = not session.closed
    release.set()
    await asyncio.gather(*calls)
    reloaded = await reload_task

    # Assert
    assert reload_pending
    assert session_open_during_reload
    assert reloaded
    assert session.closed
    assert received.empty()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not api


async def test_shutdown_action_finishes_before_client_closes(
    hass, reading_data, open_session, sdk_requests
):
    """A final reading from an HA shutdown action remains supported."""
    # Arrange
    completed = asyncio.Event()

    async def send_on_shutdown():
        await hass.services.async_call(
            DOMAIN, SERVICE_SEND_METER_READING, reading_data, blocking=True
        )
        completed.set()

    hass.async_add_shutdown_job(HassJob(send_on_shutdown))

    # Act
    await hass.async_stop()

    # Assert
    assert completed.is_set()
    assert sdk_requests.call_count == 2
    assert open_session.closed


async def test_failed_close_keeps_shutdown_cleanup(hass, loaded_entry, monkeypatch):
    """HA retains failed unload state and retries client cleanup on shutdown."""
    # Arrange
    api = loaded_entry.runtime_data
    close = AsyncMock(side_effect=[RuntimeError("Close failed"), None])
    monkeypatch.setattr(api._client, "close", close)

    # Act
    unloaded = await hass.config_entries.async_unload(loaded_entry.entry_id)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    # Assert
    assert not unloaded
    assert loaded_entry.state is ConfigEntryState.FAILED_UNLOAD
    assert loaded_entry.runtime_data is api
    assert close.await_count == 2


async def test_readings_reuse_session(
    hass, loaded_entry, reading_data, open_session, sdk_requests
):
    """Repeated readings use the same account client and HTTP session."""
    # Arrange
    api = loaded_entry.runtime_data

    # Act
    await hass.services.async_call(
        DOMAIN, SERVICE_SEND_METER_READING, reading_data, blocking=True
    )

    # Assert
    assert loaded_entry.runtime_data is api
    assert api._client._session is open_session
    assert not open_session.closed
    assert open_session.headers["Authorization"] == "Bearer old-token"
    assert sdk_requests.call_count == 2


async def test_reload_replaces_session_and_credentials(
    hass, loaded_entry, reading_data, open_session, sdk_requests
):
    """Reload closes the old session and uses the updated token."""
    # Arrange
    api = loaded_entry.runtime_data
    hass.config_entries.async_update_entry(
        loaded_entry, data={CONF_API_TOKEN: "new-token"}
    )

    # Act
    reloaded = await hass.config_entries.async_reload(loaded_entry.entry_id)
    await hass.services.async_call(
        DOMAIN, SERVICE_SEND_METER_READING, reading_data, blocking=True
    )

    # Assert
    new_session = loaded_entry.runtime_data._client._session
    assert reloaded
    assert open_session.closed
    assert loaded_entry.runtime_data is not api
    assert new_session is not open_session
    assert new_session.headers["Authorization"] == "Bearer new-token"
    assert not new_session.closed
    assert sdk_requests.call_count == 2


async def test_reload_removes_old_shutdown_listener(
    hass, loaded_entry, reading_data, open_session, monkeypatch
):
    """Shutdown closes the new client without calling the old client again."""
    # Arrange
    old_api = loaded_entry.runtime_data
    close_old = AsyncMock(wraps=old_api.async_close)
    monkeypatch.setattr(old_api, "async_close", close_old)
    assert await hass.config_entries.async_reload(loaded_entry.entry_id)
    await hass.services.async_call(
        DOMAIN, SERVICE_SEND_METER_READING, reading_data, blocking=True
    )
    new_session = loaded_entry.runtime_data._client._session

    # Act
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    # Assert
    assert open_session.closed
    assert new_session.closed
    close_old.assert_awaited_once()


async def test_stopped_client_rejects_readings(
    hass, reading_data, open_session, sdk_requests
):
    """A later action must never reopen the closed session."""
    # Arrange
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    # Act & Assert
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN, SERVICE_SEND_METER_READING, reading_data, blocking=True
        )
    assert err.value.translation_key == "no_api_token"
    assert sdk_requests.call_count == 1
    assert open_session.closed


async def test_unloading_one_account_preserves_other_session(
    hass, loaded_entry, reading_data, open_session, sdk_requests
):
    """Unloading one account leaves the other account's session usable."""
    # Arrange
    other = MockConfigEntry(domain=DOMAIN, data={CONF_API_TOKEN: "second-token"})
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    other_data = {**reading_data, "entry_id": other.entry_id}
    await hass.services.async_call(
        DOMAIN, SERVICE_SEND_METER_READING, other_data, blocking=True
    )
    other_session = other.runtime_data._client._session

    # Act
    unloaded = await hass.config_entries.async_unload(loaded_entry.entry_id)
    await hass.services.async_call(
        DOMAIN, SERVICE_SEND_METER_READING, other_data, blocking=True
    )

    # Assert
    assert unloaded
    assert open_session.closed
    assert not other_session.closed
    assert other.runtime_data._client._session is other_session
    assert open_session.headers["Authorization"] == "Bearer old-token"
    assert other_session.headers["Authorization"] == "Bearer second-token"
    assert sdk_requests.call_count == 3
    assert hass.services.has_service(DOMAIN, SERVICE_SEND_METER_READING)


@pytest.mark.parametrize(
    ("domain", "state"),
    [("other", ConfigEntryState.LOADED)]
    + [
        (DOMAIN, state)
        for state in ConfigEntryState
        if state is not ConfigEntryState.LOADED
    ],
)
async def test_service_rejects_foreign_or_unloaded_entries(hass, domain, state):
    """Never access runtime data or send a request for an unavailable account."""
    # Arrange
    entry = MockConfigEntry(
        domain=domain, state=state, data={CONF_API_TOKEN: "test-token"}
    )
    entry.add_to_hass(hass)
    await async_setup(hass, {})

    # Act & Assert
    with (
        patch(
            "custom_components.energy_tracker.EnergyTrackerApi.send_meter_reading"
        ) as send,
        pytest.raises(ServiceValidationError) as err,
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": entry.entry_id,
                "device_id": "device-123",
                "source_entity_id": "sensor.meter",
            },
            blocking=True,
        )
    assert err.value.translation_key == "no_api_token"
    send.assert_not_called()


async def test_empty_token_cannot_send_readings(hass):
    """Keep rejecting an account without credentials before making requests."""
    # Arrange
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_TOKEN: ""})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    # Act & Assert
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": entry.entry_id,
                "device_id": "device-123",
                "source_entity_id": "sensor.meter",
            },
            blocking=True,
        )
    assert err.value.translation_key == "no_api_token"
    assert entry.runtime_data._client._session is None


class TestAsyncSetup:
    """Test async_setup function."""

    async def test_async_setup_returns_true(self, hass: HomeAssistant):
        """Test that async_setup returns True (YAML not supported)."""
        # Arrange
        config = {}

        # Act
        result = await async_setup(hass, config)

        # Assert
        assert result is True
        assert hass.services.has_service(DOMAIN, SERVICE_SEND_METER_READING)


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    async def test_setup_entry_stores_client_in_runtime_data(self, hass: HomeAssistant):
        """Test that setup_entry stores the account client in runtime_data."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token-123"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)

        # Act
        result = await hass.config_entries.async_setup(entry.entry_id)

        # Assert
        assert result is True
        assert isinstance(entry.runtime_data, EnergyTrackerApi)

    async def test_setup_entry_registers_service_once(self, hass: HomeAssistant):
        """Test that service is registered only once for multiple entries."""
        # Arrange
        entry1 = MockConfigEntry(
            domain=DOMAIN,
            title="Account 1",
            data={CONF_API_TOKEN: "token-1"},
            entry_id="entry-1",
        )
        entry1.add_to_hass(hass)

        entry2 = MockConfigEntry(
            domain=DOMAIN,
            title="Account 2",
            data={CONF_API_TOKEN: "token-2"},
            entry_id="entry-2",
        )
        entry2.add_to_hass(hass)

        # Act
        await hass.config_entries.async_setup(entry1.entry_id)
        assert entry2.state is ConfigEntryState.LOADED

        # Assert
        assert hass.services.has_service(DOMAIN, SERVICE_SEND_METER_READING)
        # Service should only be registered once
        assert len(list(hass.services.async_services()[DOMAIN])) == 1


class TestAsyncUnloadEntry:
    """Test async_unload_entry function."""

    async def test_unload_entry_returns_true(self, hass: HomeAssistant):
        """Test that unload_entry returns True."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        # Act
        result = await hass.config_entries.async_unload(entry.entry_id)

        # Assert
        assert result is True

    async def test_unload_last_entry_keeps_service(self, hass: HomeAssistant):
        """Keep the action available so unloaded accounts get a validation error."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        assert hass.services.has_service(DOMAIN, SERVICE_SEND_METER_READING)

        # Act
        await hass.config_entries.async_unload(entry.entry_id)

        # Assert
        assert hass.services.has_service(DOMAIN, SERVICE_SEND_METER_READING)

    async def test_unload_one_of_multiple_entries_keeps_service(
        self, hass: HomeAssistant
    ):
        """Test that unloading one entry keeps service when others exist."""
        # Arrange
        entry1 = MockConfigEntry(
            domain=DOMAIN,
            title="Account 1",
            data={CONF_API_TOKEN: "token-1"},
            entry_id="entry-1",
        )
        entry1.add_to_hass(hass)

        entry2 = MockConfigEntry(
            domain=DOMAIN,
            title="Account 2",
            data={CONF_API_TOKEN: "token-2"},
            entry_id="entry-2",
        )
        entry2.add_to_hass(hass)

        await hass.config_entries.async_setup(entry1.entry_id)
        assert entry2.state is ConfigEntryState.LOADED

        # Act
        await hass.config_entries.async_unload(entry1.entry_id)

        # Assert
        assert hass.services.has_service(DOMAIN, SERVICE_SEND_METER_READING)
        # entry2 still has its runtime_data
        assert isinstance(entry2.runtime_data, EnergyTrackerApi)


class TestAsyncHandleSendMeterReading:
    """Test async_handle_send_meter_reading function."""

    async def test_send_meter_reading_success(self, hass: HomeAssistant):
        """Test successful meter reading submission."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        # Set up entity state
        hass.states.async_set(
            "sensor.energy_meter",
            "123.45",
            {"unit_of_measurement": "kWh"},
        )

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "test-entry-id",
                "device_id": "device-123",
                "source_entity_id": "sensor.energy_meter",
                "allow_rounding": True,
            },
        )

        # Act
        with patch(
            "custom_components.energy_tracker.EnergyTrackerApi.send_meter_reading",
            new_callable=AsyncMock,
        ) as mock_send:
            await async_handle_send_meter_reading(hass, call)

        # Assert
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["source_entity_id"] == "sensor.energy_meter"
        assert call_kwargs["device_id"] == "device-123"
        assert call_kwargs["value"] == 123.45
        assert call_kwargs["allow_rounding"] is True

    async def test_entity_not_found_raises_error(self, hass: HomeAssistant):
        """Test that non-existent entity raises localized error."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "test-entry-id",
                "device_id": "device-123",
                "source_entity_id": "sensor.nonexistent",
                "allow_rounding": True,
            },
        )

        # Act & Assert
        with pytest.raises(HomeAssistantError) as exc_info:
            await async_handle_send_meter_reading(hass, call)

        assert exc_info.value.translation_domain == DOMAIN
        assert exc_info.value.translation_key == "entity_not_found"
        assert (
            exc_info.value.translation_placeholders["entity_id"] == "sensor.nonexistent"
        )

    async def test_entity_unavailable_raises_error(self, hass: HomeAssistant):
        """Test that unavailable entity raises localized error."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        hass.states.async_set("sensor.energy_meter", STATE_UNAVAILABLE)

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "test-entry-id",
                "device_id": "device-123",
                "source_entity_id": "sensor.energy_meter",
                "allow_rounding": True,
            },
        )

        # Act & Assert
        with pytest.raises(HomeAssistantError) as exc_info:
            await async_handle_send_meter_reading(hass, call)

        assert exc_info.value.translation_domain == DOMAIN
        assert exc_info.value.translation_key == "entity_unavailable"
        assert (
            exc_info.value.translation_placeholders["entity_id"]
            == "sensor.energy_meter"
        )
        assert exc_info.value.translation_placeholders["state"] == STATE_UNAVAILABLE

    async def test_entity_unknown_raises_error(self, hass: HomeAssistant):
        """Test that unknown entity state raises localized error."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        hass.states.async_set("sensor.energy_meter", STATE_UNKNOWN)

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "test-entry-id",
                "device_id": "device-123",
                "source_entity_id": "sensor.energy_meter",
                "allow_rounding": True,
            },
        )

        # Act & Assert
        with pytest.raises(HomeAssistantError) as exc_info:
            await async_handle_send_meter_reading(hass, call)

        assert exc_info.value.translation_domain == DOMAIN
        assert exc_info.value.translation_key == "entity_unavailable"
        assert exc_info.value.translation_placeholders["state"] == STATE_UNKNOWN

    async def test_invalid_number_raises_error(self, hass: HomeAssistant):
        """Test that non-numeric entity state raises localized error."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        hass.states.async_set("sensor.energy_meter", "not_a_number")

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "test-entry-id",
                "device_id": "device-123",
                "source_entity_id": "sensor.energy_meter",
                "allow_rounding": True,
            },
        )

        # Act & Assert
        with pytest.raises(HomeAssistantError) as exc_info:
            await async_handle_send_meter_reading(hass, call)

        assert exc_info.value.translation_domain == DOMAIN
        assert exc_info.value.translation_key == "invalid_number"
        assert (
            exc_info.value.translation_placeholders["entity_id"]
            == "sensor.energy_meter"
        )
        assert exc_info.value.translation_placeholders["state"] == "not_a_number"

    async def test_missing_timestamp_raises_error(self, hass: HomeAssistant):
        """Test that entity without timestamp raises localized error."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        # Create state with None timestamp
        mock_state = MagicMock()
        mock_state.state = "123.45"
        mock_state.last_updated = None

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "test-entry-id",
                "device_id": "device-123",
                "source_entity_id": "sensor.energy_meter",
                "allow_rounding": True,
            },
        )

        # Act & Assert
        # Patch the hass.states.get call at module level
        with (
            patch("homeassistant.core.StateMachine.get", return_value=mock_state),
            pytest.raises(HomeAssistantError) as exc_info,
        ):
            await async_handle_send_meter_reading(hass, call)

        assert exc_info.value.translation_domain == DOMAIN
        assert exc_info.value.translation_key == "missing_timestamp"
        assert (
            exc_info.value.translation_placeholders["entity_id"]
            == "sensor.energy_meter"
        )

    async def test_unloaded_account_raises_error(self, hass: HomeAssistant):
        """Test that an unloaded account raises a localized error."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "valid-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        await hass.config_entries.async_unload(entry.entry_id)

        hass.states.async_set("sensor.energy_meter", "123.45")

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "test-entry-id",
                "device_id": "device-123",
                "source_entity_id": "sensor.energy_meter",
                "allow_rounding": True,
            },
        )

        # Act & Assert
        with pytest.raises(HomeAssistantError) as exc_info:
            await async_handle_send_meter_reading(hass, call)

        assert exc_info.value.translation_domain == DOMAIN
        assert exc_info.value.translation_key == "no_api_token"

    async def test_deleted_integration_raises_error(self, hass: HomeAssistant):
        """Test that deleted integration entry raises localized error."""
        # Arrange
        hass.states.async_set("sensor.energy_meter", "123.45")

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "nonexistent-entry-id",
                "device_id": "device-123",
                "source_entity_id": "sensor.energy_meter",
                "allow_rounding": True,
            },
        )

        # Act & Assert
        with pytest.raises(HomeAssistantError) as exc_info:
            await async_handle_send_meter_reading(hass, call)

        assert exc_info.value.translation_domain == DOMAIN
        assert exc_info.value.translation_key == "no_api_token"

    async def test_device_id_whitespace_stripped(self, hass: HomeAssistant):
        """Test that device_id whitespace is properly stripped."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        hass.states.async_set("sensor.energy_meter", "123.45")

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "test-entry-id",
                "device_id": "  device-123  ",
                "source_entity_id": "sensor.energy_meter",
                "allow_rounding": True,
            },
        )

        # Act
        with patch(
            "custom_components.energy_tracker.EnergyTrackerApi.send_meter_reading",
            new_callable=AsyncMock,
        ) as mock_send:
            await async_handle_send_meter_reading(hass, call)

        # Assert
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["device_id"] == "device-123"

    async def test_empty_entry_id_logs_debug(self, hass: HomeAssistant):
        """Test that empty entry_id logs debug message."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        hass.states.async_set("sensor.energy_meter", "123.45")

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "",  # Empty entry_id
                "device_id": "device-123",
                "source_entity_id": "sensor.energy_meter",
                "allow_rounding": True,
            },
        )

        # Act & Assert
        with pytest.raises(HomeAssistantError) as exc_info:
            await async_handle_send_meter_reading(hass, call)

        assert exc_info.value.translation_domain == DOMAIN
        assert exc_info.value.translation_key == "no_api_token"

    async def test_deleted_entry_logs_debug(self, hass: HomeAssistant):
        """Test that deleted integration logs debug message."""
        # Arrange
        # Set up one entry, but try to use a different (deleted) one
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="existing-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        hass.states.async_set("sensor.energy_meter", "123.45")

        call = create_service_call(
            hass,
            DOMAIN,
            SERVICE_SEND_METER_READING,
            {
                "entry_id": "deleted-entry-id",  # Different entry that was deleted
                "device_id": "device-123",
                "source_entity_id": "sensor.energy_meter",
                "allow_rounding": True,
            },
        )

        # Act & Assert
        with pytest.raises(HomeAssistantError) as exc_info:
            await async_handle_send_meter_reading(hass, call)

        assert exc_info.value.translation_domain == DOMAIN
        assert exc_info.value.translation_key == "no_api_token"

    async def test_service_wrapper_function(self, hass: HomeAssistant):
        """Test that registered service wrapper calls handler correctly."""
        # Arrange
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Account",
            data={CONF_API_TOKEN: "test-token"},
            entry_id="test-entry-id",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)

        hass.states.async_set("sensor.energy_meter", "123.45")

        # Act
        with patch(
            "custom_components.energy_tracker.EnergyTrackerApi.send_meter_reading",
            new_callable=AsyncMock,
        ) as mock_send:
            # Call via the registered service (which uses the wrapper)
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SEND_METER_READING,
                {
                    "entry_id": "test-entry-id",
                    "device_id": "device-123",
                    "source_entity_id": "sensor.energy_meter",
                    "allow_rounding": True,
                },
                blocking=True,
            )

        # Assert
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["device_id"] == "device-123"
        assert call_kwargs["value"] == 123.45
