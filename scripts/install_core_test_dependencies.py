"""Install dependencies for running the exported tests in a Core checkout."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def core_test_requirements(core_root: Path) -> list[str]:
    """Use Core's pins for dependencies imported by its shared test fixtures."""
    lines = (core_root / "requirements_all.txt").read_text().splitlines()
    requirements = []
    for name in ("paho-mqtt", "aiohasupervisor"):
        matches = [line for line in lines if line.startswith(f"{name}==")]
        if len(matches) != 1:
            raise ValueError(f"Expected one {name} pin in Core requirements_all.txt")
        requirements.extend(matches)
    return requirements


def install(core_root: Path) -> None:
    """Install the Core runtime, test tools, shared fixtures and integration SDK."""
    manifest = json.loads(
        (PROJECT_ROOT / "custom_components/energy_tracker/manifest.json").read_text()
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "-e",
            str(core_root),
            "-r",
            str(core_root / "requirements.txt"),
            "-r",
            str(core_root / "requirements_test.txt"),
            *core_test_requirements(core_root),
            *manifest["requirements"],
        ],
        check=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("core_root", type=Path)
    args = parser.parse_args()
    install(args.core_root.resolve())
