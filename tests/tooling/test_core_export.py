"""Verify the actual Core export without publishing or modifying a Core fork."""

import ast
import json
from pathlib import Path

import pytest
from scripts.export_to_core import export_to_core, remove_custom_test_setup

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_core_export_contains_only_integration_files(tmp_path: Path) -> None:
    """Export valid metadata and integration tests with no local tooling imports."""
    original_manifest = (
        PROJECT_ROOT / "custom_components/energy_tracker/manifest.json"
    ).read_text()
    original_conftest = (PROJECT_ROOT / "tests/conftest.py").read_text()
    export_to_core(PROJECT_ROOT, tmp_path)

    component = tmp_path / "homeassistant/components/energy_tracker"
    tests = tmp_path / "tests/components/energy_tracker"
    assert not (tests / "tooling").exists()
    assert sorted(path.name for path in tests.glob("test_*.py")) == [
        "test_api.py",
        "test_config_flow.py",
        "test_init.py",
    ]
    for directory in (component, tests):
        assert not list(directory.rglob("__pycache__"))
        for path in directory.rglob("*.json"):
            json.loads(path.read_text())
        for path in directory.rglob("*.py"):
            source = path.read_text()
            ast.parse(source)
            assert "custom_components.energy_tracker" not in source
            assert "pytest_homeassistant_custom_component" not in source
            assert "from scripts" not in source

    manifest = json.loads((component / "manifest.json").read_text())
    assert "version" not in manifest
    assert "issue_tracker" not in manifest
    assert manifest["requirements"] == json.loads(original_manifest)["requirements"]
    assert manifest["documentation"] == (
        "https://www.home-assistant.io/integrations/energy_tracker/"
    )
    flow = (component / "config_flow.py").read_text()
    assert "class EnergyTrackerConfigFlow(ConfigFlow, domain=DOMAIN)" in flow
    assert "-> ConfigFlowResult:" in flow
    assert "from homeassistant.data_entry_flow import AbortFlow\n" in flow
    assert "AbortFlow, FlowResult" not in flow
    conftest = (tests / "conftest.py").read_text()
    assert "auto_enable_custom_integrations" not in conftest
    assert "def api_token" in conftest
    assert "def device_id" in conftest
    assert (
        '"homeassistant.components.energy_tracker.api.EnergyTrackerClient"'
        in (tests / "test_api.py").read_text()
    )
    abort = json.loads((component / "strings.json").read_text())["config"]["abort"]
    assert abort["already_configured"].startswith("[%key:common::")
    assert abort["reconfigure_successful"].startswith("[%key:common::")
    assert (
        PROJECT_ROOT / "custom_components/energy_tracker/manifest.json"
    ).read_text() == original_manifest
    assert (PROJECT_ROOT / "tests/conftest.py").read_text() == original_conftest


def test_repeated_export_removes_stale_files_only_from_this_integration(
    tmp_path: Path,
) -> None:
    """A repeat export replaces stale integration files and preserves other code."""
    export_to_core(PROJECT_ROOT, tmp_path)
    component = tmp_path / "homeassistant/components/energy_tracker"
    tests = tmp_path / "tests/components/energy_tracker"
    (component / "obsolete.py").write_text("old component")
    (tests / "test_obsolete.py").write_text("old test")
    other = tmp_path / "homeassistant/components/other.py"
    other.write_text("unrelated")

    export_to_core(PROJECT_ROOT, tmp_path)

    assert not (component / "obsolete.py").exists()
    assert not (tests / "test_obsolete.py").exists()
    assert other.read_text() == "unrelated"


def test_custom_fixture_removal_preserves_other_autouse_fixtures(
    tmp_path: Path,
) -> None:
    """Remove the named fixture by syntax, without deleting unrelated fixtures."""
    path = tmp_path / "conftest.py"
    path.write_text('''import pytest
pytest_plugins = "pytest_homeassistant_custom_component"

@pytest.fixture(
    autouse=True,
)
def auto_enable_custom_integrations(enable_custom_integrations):
    """A fixture with a multiline decorator and body."""
    enabled = enable_custom_integrations
    return enabled

@pytest.fixture(autouse=True)
def retain_this_fixture():
    return True
''')
    remove_custom_test_setup(path)
    result = path.read_text()
    ast.parse(result)
    assert "pytest_plugins" not in result
    assert "auto_enable_custom_integrations" not in result
    assert "@pytest.fixture(autouse=True)" in result
    assert "def retain_this_fixture" in result


def test_export_rejects_destination_inside_source_before_copying(
    tmp_path: Path,
) -> None:
    """An invalid destination must not create or overwrite any source files."""
    with pytest.raises(ValueError, match="Export destination must be outside"):
        export_to_core(tmp_path, tmp_path)
    assert list(tmp_path.iterdir()) == []
