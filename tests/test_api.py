"""Tests for the Energy Tracker API wrapper."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from energy_tracker_api import (
    AuthenticationError,
    ConflictError,
    EnergyTrackerAPIError,
    ForbiddenError,
    NetworkError,
    RateLimitError,
    ResourceNotFoundError,
    TimeoutError,
    ValidationError,
)
from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.energy_tracker.api import EnergyTrackerApi


async def test_close_drains_requests_after_cancellation_and_failure():
    """Canceled and failed writes must release the client without admitting new ones."""
    # Arrange
    entered = asyncio.Event()
    release = asyncio.Event()
    started = 0

    async def request(**kwargs):
        nonlocal started
        started += 1
        if started == 2:
            entered.set()
        await release.wait()
        raise TimeoutError("Request timed out")

    with patch("custom_components.energy_tracker.api.EnergyTrackerClient") as client:
        client.return_value.meter_readings.create = AsyncMock(side_effect=request)
        client.return_value.close = AsyncMock()
        api = EnergyTrackerApi(token="test-token")
        data = {
            "source_entity_id": "sensor.meter",
            "device_id": "device-123",
            "value": 123.45,
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        }
        tasks = [asyncio.create_task(api.send_meter_reading(**data)) for _ in range(2)]
        close_task = None
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)

            # Act
            close_task = asyncio.create_task(api.async_close())
            await asyncio.sleep(0)
            close_pending_before_cancel = not close_task.done()
            with pytest.raises(HomeAssistantError) as rejected_call:
                await api.send_meter_reading(**data)
            tasks[0].cancel()
            with pytest.raises(asyncio.CancelledError):
                await tasks[0]
            close_pending_after_cancel = not close_task.done()
            close_calls_while_pending = client.return_value.close.await_count
            release.set()
            with pytest.raises(HomeAssistantError) as timed_out_call:
                await tasks[1]
            await asyncio.wait_for(close_task, timeout=5)

            # Assert
            assert close_pending_before_cancel
            assert close_pending_after_cancel
            assert close_calls_while_pending == 0
            assert rejected_call.value.translation_key == "no_api_token"
            assert timed_out_call.value.translation_key == "timeout"
            client.return_value.close.assert_awaited_once()
            assert started == 2
        finally:
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            if close_task:
                await close_task


class TestEnergyTrackerApiInit:
    """Test EnergyTrackerApi initialization."""

    def test_init_creates_client(self, hass, api_token):
        """Test that __init__ creates EnergyTrackerClient."""
        # Arrange & Act
        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client:
            api = EnergyTrackerApi(token=api_token)

            # Assert
            mock_client.assert_called_once_with(access_token=api_token)
            assert api._client == mock_client.return_value


class TestSendMeterReading:
    """Test send_meter_reading method."""

    @pytest.mark.asyncio
    async def test_send_meter_reading_success(self, hass, api_token, device_id):
        """Test successful meter reading submission."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.meter_readings.create = AsyncMock()
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act
            await api.send_meter_reading(
                source_entity_id="sensor.power_meter",
                device_id=device_id,
                value=1234.5,
                timestamp=timestamp,
                allow_rounding=True,
            )

            # Assert
            mock_client.meter_readings.create.assert_called_once()
            call_args = mock_client.meter_readings.create.call_args
            assert call_args[1]["device_id"] == device_id
            assert call_args[1]["meter_reading"].value == 1234.5
            assert call_args[1]["meter_reading"].timestamp == timestamp
            assert call_args[1]["allow_rounding"] is True

    @pytest.mark.asyncio
    async def test_send_meter_reading_without_rounding(
        self, hass, api_token, device_id
    ):
        """Test meter reading submission without rounding."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.meter_readings.create = AsyncMock()
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act
            await api.send_meter_reading(
                source_entity_id="sensor.power_meter",
                device_id=device_id,
                value=1234.5,
                timestamp=timestamp,
                allow_rounding=False,
            )

            # Assert
            call_args = mock_client.meter_readings.create.call_args
            assert call_args[1]["allow_rounding"] is False

    @pytest.mark.asyncio
    async def test_send_meter_reading_validation_error(
        self, hass, api_token, device_id
    ):
        """Test meter reading with validation error (HTTP 400)."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = ValidationError(
                "Bad Request", api_message=["Invalid timestamp", "Value required"]
            )
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "bad_request"
            assert (
                exc_info.value.translation_placeholders["error"]
                == "Invalid timestamp; Value required"
            )

    @pytest.mark.asyncio
    async def test_send_meter_reading_authentication_error(
        self, hass, api_token, device_id
    ):
        """Test meter reading with authentication error (HTTP 401)."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = AuthenticationError("Unauthorized")
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "auth_failed"

    @pytest.mark.asyncio
    async def test_send_meter_reading_forbidden_error(self, hass, api_token, device_id):
        """Test meter reading with forbidden error (HTTP 403)."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = ForbiddenError("Forbidden")
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "auth_failed"

    @pytest.mark.asyncio
    async def test_send_meter_reading_not_found_error(self, hass, api_token, device_id):
        """Test meter reading with not found error (HTTP 404)."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = ResourceNotFoundError("Not Found")
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "device_not_found"

    @pytest.mark.asyncio
    async def test_send_meter_reading_conflict_error(self, hass, api_token, device_id):
        """Test meter reading with conflict error (HTTP 409)."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = ConflictError("Duplicate reading")
            error.api_message = ["Reading already exists"]
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "conflict"
            assert (
                "Reading already exists"
                in exc_info.value.translation_placeholders["error"]
            )

    @pytest.mark.asyncio
    async def test_send_meter_reading_rate_limit_with_retry(
        self, hass, api_token, device_id
    ):
        """Test meter reading with rate limit error including retry_after."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = RateLimitError("Too Many Requests", retry_after=60)
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "rate_limit"
            assert exc_info.value.translation_placeholders["retry_after"] == "60"

    @pytest.mark.asyncio
    async def test_send_meter_reading_rate_limit_without_retry(
        self, hass, api_token, device_id
    ):
        """Test meter reading with rate limit error without retry_after."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = RateLimitError("Too Many Requests", retry_after=None)
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "rate_limit_no_time"

    @pytest.mark.asyncio
    async def test_send_meter_reading_timeout_error(self, hass, api_token, device_id):
        """Test meter reading with timeout error."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = TimeoutError("Request timeout")
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "timeout"

    @pytest.mark.asyncio
    async def test_send_meter_reading_network_error(self, hass, api_token, device_id):
        """Test meter reading with network error."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = NetworkError("Network unreachable")
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "network_error"

    @pytest.mark.asyncio
    async def test_send_meter_reading_server_error(self, hass, api_token, device_id):
        """Test meter reading with server error (5xx)."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = EnergyTrackerAPIError(
                "Server error: 500", api_message=["Database unavailable"]
            )
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "server_error"
            assert (
                exc_info.value.translation_placeholders["error"]
                == "Database unavailable"
            )

    @pytest.mark.asyncio
    async def test_send_meter_reading_unexpected_error(
        self, hass, api_token, device_id
    ):
        """Test meter reading with unexpected error."""
        # Arrange
        timestamp = datetime(2025, 11, 28, 10, 30, 0, tzinfo=UTC)

        with patch(
            "custom_components.energy_tracker.api.EnergyTrackerClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            error = RuntimeError("Something went wrong")
            mock_client.meter_readings.create = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            api = EnergyTrackerApi(token=api_token)

            # Act & Assert
            with pytest.raises(HomeAssistantError) as exc_info:
                await api.send_meter_reading(
                    source_entity_id="sensor.power_meter",
                    device_id=device_id,
                    value=1234.5,
                    timestamp=timestamp,
                )

            assert exc_info.value.translation_key == "unknown_error"
            assert (
                exc_info.value.translation_placeholders["error"]
                == "Something went wrong"
            )
