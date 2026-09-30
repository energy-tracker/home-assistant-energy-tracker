"""Regression tests for dependency updates and manifest pins."""

import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from scripts import sync_dependencies


@pytest.fixture
def dependency_project(tmp_path: Path) -> Path:
    """Create a project whose old lock must survive failed updates."""
    manifest = tmp_path / "custom_components/energy_tracker/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"requirements": ["energy-tracker-api==1.0.0"]}))
    (tmp_path / "requirements-dev.txt").write_text("energy-tracker-api>=1.0.0,<2.0.0\n")
    (tmp_path / "requirements-dev.lock").write_text("previous lock\n")
    return tmp_path


@pytest.mark.parametrize("failed_step", [0, 1])
def test_failed_update_preserves_lock(
    dependency_project: Path, failed_step: int
) -> None:
    """Neither resolution errors nor a broken environment may replace the lock."""
    results = [None] * failed_step + [subprocess.CalledProcessError(1, "pip")]
    with (
        patch.object(sync_dependencies, "PROJECT_ROOT", dependency_project),
        patch.object(sync_dependencies.subprocess, "run", side_effect=results),
        pytest.raises(subprocess.CalledProcessError),
    ):
        sync_dependencies.main()

    assert (
        dependency_project / "requirements-dev.lock"
    ).read_text() == "previous lock\n"


def test_update_respects_manifest_and_records_versions(
    dependency_project: Path,
) -> None:
    """Resolve all requirements together without constraining updates to the old lock."""
    with (
        patch.object(sync_dependencies, "PROJECT_ROOT", dependency_project),
        patch.object(sync_dependencies.subprocess, "run") as run,
        patch.object(sync_dependencies, "version", return_value="1.0.0"),
    ):
        sync_dependencies.main()

    install = run.call_args_list[0].args[0]
    assert install[install.index("-r") + 1] == "requirements-dev.txt"
    assert "energy-tracker-api==1.0.0" in install
    assert "requirements-dev.lock" not in install
    assert run.call_args_list[1].args[0][-2:] == ["pip", "check"]
    pins = (dependency_project / "requirements-dev.lock").read_text()
    assert "energy-tracker-api==1.0.0\n" in pins
    assert "homeassistant==1.0.0\n" in pins
