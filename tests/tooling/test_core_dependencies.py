"""Test dependency setup for Core exports without installing packages."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from scripts import install_core_test_dependencies as installer


def test_installer_uses_core_and_manifest_pins(tmp_path: Path, monkeypatch) -> None:
    """Use the target Core's fixture pins and the integration's SDK requirement."""
    # Arrange
    core = tmp_path / "core"
    core.mkdir()
    (core / "requirements_all.txt").write_text(
        "paho-mqtt==2.1.0\naiohasupervisor==0.6.0\nunrelated==1.0\n"
    )
    run = Mock()
    monkeypatch.setattr(installer.subprocess, "run", run)
    manifest = json.loads(
        (
            installer.PROJECT_ROOT / "custom_components/energy_tracker/manifest.json"
        ).read_text()
    )

    # Act
    installer.install(core)

    # Assert
    run.assert_called_once()
    command = run.call_args.args[0]
    assert command[:6] == [
        installer.sys.executable,
        "-m",
        "uv",
        "pip",
        "install",
        "--python",
    ]
    assert command[6] == installer.sys.executable
    assert command[7:13] == [
        "-e",
        str(core),
        "-r",
        str(core / "requirements.txt"),
        "-r",
        str(core / "requirements_test.txt"),
    ]
    assert command[13:] == [
        "paho-mqtt==2.1.0",
        "aiohasupervisor==0.6.0",
        *manifest["requirements"],
    ]
    assert run.call_args.kwargs == {"check": True}


@pytest.mark.parametrize(
    "pins",
    [
        "",
        "paho-mqtt==2.1.0\n",
        "paho-mqtt==2.1.0\npaho-mqtt==2.2.0\naiohasupervisor==0.6.0\n",
    ],
)
def test_installer_rejects_missing_or_ambiguous_pins(
    tmp_path: Path, monkeypatch, pins: str
) -> None:
    """Stop before installation when upstream dependency definitions change."""
    # Arrange
    (tmp_path / "requirements_all.txt").write_text(pins)
    run = Mock()
    monkeypatch.setattr(installer.subprocess, "run", run)

    # Act & Assert
    with pytest.raises(ValueError, match="Expected one"):
        installer.install(tmp_path)
    run.assert_not_called()
