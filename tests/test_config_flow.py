"""Test the Energy Tracker config flow."""

from __future__ import annotations

from hashlib import sha256
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.energy_tracker.const import CONF_API_TOKEN, DOMAIN


async def test_user_form_create_entry(hass: HomeAssistant) -> None:
    """Test creating a new config entry via user flow."""
    # Arrange
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Act
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "John's Account",
            CONF_API_TOKEN: "test-token-123",
        },
    )

    # Assert
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "John's Account"
    assert result2["version"] == 2
    assert result2["result"].unique_id == sha256(b"test-token-123").hexdigest()
    assert "test-token-123" not in repr(result2["result"])
    assert result2["data"] == {
        CONF_API_TOKEN: "test-token-123",
    }


@pytest.mark.parametrize("disabled_by", [None, ConfigEntryDisabler.USER])
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("stored_token", ["duplicate-token", " \tduplicate-token\n"])
@pytest.mark.parametrize("submitted_token", ["duplicate-token", " duplicate-token "])
async def test_user_form_duplicate_token(
    hass: HomeAssistant, version: int, disabled_by, stored_token, submitted_token
) -> None:
    """Test abort when token already configured."""
    # Arrange
    existing_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Energy Tracker",
        data={CONF_API_TOKEN: stored_token},
        unique_id=(
            stored_token if version == 1 else sha256(stored_token.encode()).hexdigest()
        ),
        version=version,
        disabled_by=disabled_by,
    )
    existing_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Act
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Test Account",
            CONF_API_TOKEN: submitted_token,
        },
    )

    # Assert
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_reconfigure_form_update_token(hass: HomeAssistant) -> None:
    """Test reconfiguring to update the token."""
    # Arrange
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Energy Tracker",
        data={CONF_API_TOKEN: "old-token"},
        unique_id="old-token",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry.entry_id,
        },
    )

    # Act
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload"
    ) as mock_reload:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_TOKEN: "new-token-456",
            },
        )

    # Assert
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reconfigure_successful"
    assert entry.data == {
        CONF_API_TOKEN: "new-token-456",
    }
    assert entry.unique_id == sha256(b"new-token-456").hexdigest()
    mock_reload.assert_called_once_with(entry.entry_id)


@pytest.mark.parametrize("disabled_by", [None, ConfigEntryDisabler.USER])
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("stored_token", ["token-1", " \ttoken-1\n"])
@pytest.mark.parametrize("submitted_token", ["token-1", " token-1 "])
async def test_reconfigure_form_duplicate_token(
    hass: HomeAssistant,
    version: int,
    disabled_by,
    stored_token,
    submitted_token,
    monkeypatch,
) -> None:
    """Test abort when reconfigure token conflicts with another entry."""
    # Arrange
    entry1 = MockConfigEntry(
        domain=DOMAIN,
        title="Energy Tracker",
        data={CONF_API_TOKEN: stored_token},
        unique_id=stored_token
        if version == 1
        else sha256(stored_token.encode()).hexdigest(),
        version=version,
        disabled_by=disabled_by,
    )
    entry1.add_to_hass(hass)

    entry2 = MockConfigEntry(
        domain=DOMAIN,
        title="Energy Tracker",
        data={CONF_API_TOKEN: "token-2"},
        unique_id="token-2",
    )
    entry2.add_to_hass(hass)
    reload = AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": "reconfigure",
            "entry_id": entry2.entry_id,
        },
    )

    # Act
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_API_TOKEN: submitted_token,
        },
    )

    # Assert
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"
    assert entry2.data == {CONF_API_TOKEN: "token-2"}
    assert entry2.unique_id == "token-2"
    reload.assert_not_called()


async def test_reconfigure_unchanged_token(hass: HomeAssistant, monkeypatch) -> None:
    """Re-entering the same token must not flag the account as a duplicate."""
    # Arrange
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: "same-token"},
        unique_id=sha256(b"same-token").hexdigest(),
        version=2,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    reload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)

    # Act
    updated = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_TOKEN: "same-token"}
    )

    # Assert
    assert updated["type"] == FlowResultType.ABORT
    assert updated["reason"] == "reconfigure_successful"
    assert entry.unique_id == sha256(b"same-token").hexdigest()
    reload.assert_awaited_once_with(entry.entry_id)


async def test_reconfigure_form_does_not_expose_token(hass: HomeAssistant) -> None:
    """The configuration form must not send the stored token as a default."""
    # Arrange
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_TOKEN: "secret-token"})
    entry.add_to_hass(hass)

    # Act
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )

    # Assert
    token_field = next(iter(result["data_schema"].schema))
    assert token_field.default is vol.UNDEFINED


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("stored_token", ["old-token", " old-token "])
@pytest.mark.parametrize(
    "token", ["old-token", "new-token", " old-token ", " new-token "]
)
async def test_reconfigure_unloaded_entry(hass, version, token, stored_token):
    """Reload and migrate unloaded accounts for unchanged and replaced tokens."""
    # Arrange
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_TOKEN: stored_token},
        unique_id=stored_token
        if version == 1
        else sha256(stored_token.encode()).hexdigest(),
        version=version,
    )
    entry.add_to_hass(hass)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )

    # Act
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_TOKEN: token}
    )
    await hass.async_block_till_done()

    # Assert
    assert result["reason"] == "reconfigure_successful"
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.version == 2
    assert entry.unique_id == sha256(token.strip().encode()).hexdigest()
    assert entry.data == {CONF_API_TOKEN: token.strip()}


@pytest.mark.parametrize("name", ["Account", " Account ", "\tAccount\n"])
@pytest.mark.parametrize("token", ["test-token", " test-token ", "\ttest-token\n"])
@pytest.mark.parametrize("initial_data", [False, True])
async def test_user_input_is_normalized(hass, name, token, initial_data):
    """Normalize names and tokens before storage and identity creation."""
    # Arrange
    data = {CONF_NAME: name, CONF_API_TOKEN: token}
    flow = None
    if not initial_data:
        flow = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

    # Act
    if initial_data:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=data
        )
    else:
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], data)

    # Assert
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Account"
    assert result["data"] == {CONF_API_TOKEN: "test-token"}
    assert result["result"].unique_id == sha256(b"test-token").hexdigest()
    assert data == {CONF_NAME: name, CONF_API_TOKEN: token}


@pytest.mark.parametrize("name", ["Account", "", " \t\n", "\u00a0"])
@pytest.mark.parametrize("token", ["", " \t\n", "\u00a0"])
async def test_user_form_rejects_blank_fields(hass, name, token):
    """Keep blank submissions editable without creating a broken entry."""
    # Arrange
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    expected_errors = {CONF_API_TOKEN: "required"}
    if not name.strip():
        expected_errors[CONF_NAME] = "required"

    # Act
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_NAME: name, CONF_API_TOKEN: token}
    )

    # Assert
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == expected_errors
    assert hass.config_entries.async_entries(DOMAIN) == []
    for field in result["data_schema"].schema:
        assert field.default is vol.UNDEFINED


async def test_user_form_can_correct_blank_name(hass):
    """A valid token with an empty name stays editable and can then be saved."""
    # Arrange
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_NAME: " ", CONF_API_TOKEN: " token "},
    )
    assert flow["type"] is FlowResultType.FORM
    assert flow["errors"] == {CONF_NAME: "required"}
    assert hass.config_entries.async_entries(DOMAIN) == []

    # Act
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_NAME: " Account ", CONF_API_TOKEN: " token "}
    )

    # Assert
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Account"
    assert result["data"] == {CONF_API_TOKEN: "token"}


@pytest.mark.parametrize("token", ["", " \t\n", "\u00a0"])
async def test_reconfigure_blank_token_preserves_loaded_account(
    hass, token, monkeypatch
):
    """A validation error leaves the loaded client, credentials and identity intact."""
    # Arrange
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Account",
        version=2,
        unique_id=sha256(b"old-token").hexdigest(),
        data={CONF_API_TOKEN: "old-token"},
        options={"preserved": True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    api = entry.runtime_data
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    reload = AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)

    # Act
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_TOKEN: token}
    )
    await hass.async_block_till_done()

    # Assert
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {CONF_API_TOKEN: "required"}
    assert entry.data == {CONF_API_TOKEN: "old-token"}
    assert entry.unique_id == sha256(b"old-token").hexdigest()
    assert entry.title == "Account"
    assert entry.options == {"preserved": True}
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.runtime_data is api
    assert not api._closed
    assert next(iter(result["data_schema"].schema)).default is vol.UNDEFINED
    reload.assert_not_called()


async def test_reconfigure_can_correct_blank_token(hass):
    """Correcting an empty submission applies only the final normalized token."""
    # Arrange
    entry = MockConfigEntry(
        domain=DOMAIN, version=2, data={CONF_API_TOKEN: "old-token"}
    )
    entry.add_to_hass(hass)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    invalid = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_TOKEN: " "}
    )
    assert invalid["errors"] == {CONF_API_TOKEN: "required"}

    # Act
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_API_TOKEN: " new-token "}
    )
    await hass.async_block_till_done()

    # Assert
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_API_TOKEN: "new-token"}
    assert entry.unique_id == sha256(b"new-token").hexdigest()
    assert entry.state is config_entries.ConfigEntryState.LOADED


@pytest.mark.parametrize(
    "existing_data",
    [
        {CONF_API_TOKEN: "other-token"},
        {CONF_API_TOKEN: " Token "},
        {CONF_API_TOKEN: None},
        {},
    ],
)
async def test_different_or_incomplete_account_does_not_block_setup(
    hass, existing_data
):
    """Allow another account without changing existing or incomplete credentials."""
    # Arrange
    existing = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data=existing_data,
        disabled_by=ConfigEntryDisabler.USER,
    )
    existing.add_to_hass(hass)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Act
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_NAME: "Account", CONF_API_TOKEN: " token "}
    )

    # Assert
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_API_TOKEN: "token"}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2
    assert existing.data == existing_data
    assert existing.disabled_by is ConfigEntryDisabler.USER


async def test_parallel_user_forms_cannot_create_normalized_duplicates(hass):
    """Two open forms cannot configure the same token with different whitespace."""
    # Arrange
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Act
    created = await hass.config_entries.flow.async_configure(
        first["flow_id"], {CONF_NAME: "First", CONF_API_TOKEN: " token "}
    )
    duplicate = await hass.config_entries.flow.async_configure(
        second["flow_id"], {CONF_NAME: "Second", CONF_API_TOKEN: "\ttoken\n"}
    )

    # Assert
    assert created["type"] is FlowResultType.CREATE_ENTRY
    assert duplicate["reason"] == "already_configured"
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].title == "First"
    assert entries[0].data == {CONF_API_TOKEN: "token"}
