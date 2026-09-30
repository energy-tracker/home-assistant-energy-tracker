"""Common fixtures for Energy Tracker tests."""

from __future__ import annotations

import asyncio

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
async def start_task():
    """Start test tasks and clean them up even when an assertion fails."""
    tasks = []

    def start(coroutine):
        task = asyncio.create_task(coroutine)
        tasks.append(task)
        return task

    try:
        yield start
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    return


@pytest.fixture
def api_token() -> str:
    """Return a test API token."""
    return "test-token-12345678"


@pytest.fixture
def device_id() -> str:
    """Return a valid UUID device ID."""
    return "12345678-1234-1234-1234-123456789abc"
