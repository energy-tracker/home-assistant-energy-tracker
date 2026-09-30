"""Regression tests for the Home Assistant release used by Ruff sync."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts import sync_ruff_config


def test_fetch_uses_locked_home_assistant_release(tmp_path: Path) -> None:
    """Updating the HA pin must also change the source of the Ruff configuration."""
    lock = tmp_path / "requirements-dev.lock"
    for version in ("2026.1.1", "2026.2.3"):
        lock.write_text(f"ruff==0.14.13\nhomeassistant=={version}\n")
        with (
            patch.object(sync_ruff_config, "PROJECT_ROOT", tmp_path),
            patch.object(
                sync_ruff_config.urllib.request,
                "urlopen",
                return_value=BytesIO(b'requires-python = ">=3.13.2"\n'),
            ) as fetch,
        ):
            config = sync_ruff_config.fetch_core_config()

        fetch.assert_called_once_with(
            f"https://raw.githubusercontent.com/home-assistant/core/{version}/pyproject.toml",
            timeout=30,
        )
        assert sync_ruff_config.extract_python_version(config) == "3.13"


@pytest.mark.parametrize(
    "lock",
    [
        "ruff==0.14.13\n",
        "homeassistant==\n",
        "homeassistant==2026.1.1\nhomeassistant==2026.2.3\n",
    ],
)
def test_invalid_ha_pin_fails_without_fetching_dev(tmp_path: Path, lock: str) -> None:
    """A missing or ambiguous version must never fall back to the moving dev branch."""
    (tmp_path / "requirements-dev.lock").write_text(lock)
    with (
        patch.object(sync_ruff_config, "PROJECT_ROOT", tmp_path),
        patch.object(sync_ruff_config.urllib.request, "urlopen") as fetch,
        pytest.raises(ValueError, match="one homeassistant== pin"),
    ):
        sync_ruff_config.fetch_core_config()
    fetch.assert_not_called()
