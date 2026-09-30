"""Export the integration and its tests into a Home Assistant Core checkout."""

import argparse
import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path


def remove_custom_test_setup(path: Path) -> None:
    """Remove only the custom-component plugin and its enabling fixture."""
    source = path.read_text()
    lines = source.splitlines(keepends=True)
    for node in reversed(ast.parse(source).body):
        is_plugin = isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytest_plugins"
            for target in node.targets
        )
        is_fixture = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name == "auto_enable_custom_integrations"
        )
        if is_plugin or is_fixture:
            start = node.lineno
            if is_fixture:
                start = min([start, *(item.lineno for item in node.decorator_list)])
            del lines[start - 1 : node.end_lineno]
    path.write_text("".join(lines))


def write_json(path: Path, data: dict) -> None:
    """Write valid JSON after applying Core-specific metadata changes."""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def export_to_core(source_root: Path, core_root: Path) -> None:
    """Copy and adapt integration files without exporting repository tooling."""
    component = core_root / "homeassistant/components/energy_tracker"
    tests = core_root / "tests/components/energy_tracker"
    copies = (
        (source_root / "custom_components/energy_tracker", component),
        (source_root / "tests", tests),
    )
    for source, target in copies:
        if target.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"Export destination must be outside {source}")
    for source, target in copies:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(
            source,
            target,
            ignore=shutil.ignore_patterns(
                "tooling", "translations", "__pycache__", "*.pyc"
            ),
        )

    for directory in (component, tests):
        for path in directory.rglob("*.py"):
            text = path.read_text()
            text = text.replace(
                "custom_components.energy_tracker",
                "homeassistant.components.energy_tracker",
            ).replace("pytest_homeassistant_custom_component.common", "tests.common")
            text = text.replace("  # type: ignore[call-arg]", "")
            text = text.replace("from __future__ import annotations\n\n", "")
            text = text.replace("import voluptuous as vol", "import probatio")
            text = text.replace("vol.", "probatio.")
            path.write_text(text)

    flow = component / "config_flow.py"
    text = flow.read_text()
    text = text.replace(
        "from homeassistant import config_entries",
        "from homeassistant.config_entries import ConfigFlow, ConfigFlowResult",
    ).replace(
        "from homeassistant.data_entry_flow import AbortFlow, FlowResult\n",
        "from homeassistant.data_entry_flow import AbortFlow\n",
    )
    text = text.replace("config_entries.ConfigFlow", "ConfigFlow")
    text = text.replace("-> FlowResult:", "-> ConfigFlowResult:")
    flow.write_text(text)
    remove_custom_test_setup(tests / "conftest.py")

    path = component / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.pop("version", None)
    manifest.pop("issue_tracker", None)
    manifest["documentation"] = (
        "https://www.home-assistant.io/integrations/energy_tracker/"
    )
    write_json(path, manifest)

    path = component / "strings.json"
    strings = json.loads(path.read_text())
    strings["config"]["abort"]["already_configured"] = (
        "[%key:common::config_flow::abort::already_configured_account%]"
    )
    strings["config"]["abort"]["reconfigure_successful"] = (
        "[%key:common::config_flow::abort::reconfigure_successful%]"
    )
    write_json(path, strings)

    for directory in (component, tests):
        for path in directory.rglob("*.json"):
            json.loads(path.read_text())
        for path in directory.rglob("*.py"):
            ast.parse(path.read_text(), filename=str(path))

    subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--select",
            "I",
            "--fix",
            "--config",
            "lint.isort.force-sort-within-sections = true",
            "--config",
            'lint.isort.known-first-party = ["homeassistant"]',
            "--config",
            'lint.isort.known-local-folder = ["tests"]',
            "--config",
            "lint.isort.combine-as-imports = true",
            "--config",
            "lint.isort.split-on-trailing-comma = false",
            str(component),
            str(tests),
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--isolated",
            str(component),
            str(tests),
        ],
        check=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("core_root", type=Path)
    args = parser.parse_args()
    export_to_core(Path(__file__).resolve().parents[1], args.core_root.resolve())
