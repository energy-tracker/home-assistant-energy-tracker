"""Update development dependencies while preserving manifest requirements."""

from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCKED_PACKAGES = (
    "energy-tracker-api",
    "homeassistant",
    "mypy",
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "pytest-homeassistant-custom-component",
    "ruff",
)


def main() -> None:
    """Resolve requirements together, then record the validated environment."""
    manifest = json.loads(
        (PROJECT_ROOT / "custom_components/energy_tracker/manifest.json").read_text()
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "-r",
            "requirements-dev.txt",
            *manifest["requirements"],
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)

    pins = "".join(f"{name}=={version(name)}\n" for name in LOCKED_PACKAGES)
    (PROJECT_ROOT / "requirements-dev.lock").write_text(pins)


if __name__ == "__main__":
    main()
