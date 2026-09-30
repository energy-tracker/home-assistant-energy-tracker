# Contributing

## Development checks

CI and `make install` use `requirements-dev.lock` as constraints for the test tools,
Home Assistant and the API client. CI reads the Python version from the matching
Home Assistant release. The current test baseline is Home Assistant 2026.1.1 on Python 3.13.

```bash
make venv PYTHON=python3.13
make install
make test
```

`make sync-deps` updates development dependencies within `requirements-dev.txt`
and the integration's manifest requirements. It checks the resulting environment
before writing `requirements-dev.lock`; changing the SDK requires updating its
manifest pin and the development requirement together.
Ruff configuration and Python targets are synced from that same locked Home Assistant
release, including when running `make sync-ruff` on its own.

## Release Process

### HACS Release

1. Update `version` in `custom_components/energy_tracker/manifest.json`
2. Commit and push changes
3. Create and push tag:
   ```bash
   git tag v1.2.3
   git push origin v1.2.3
   ```
4. GitHub Action validates the manifest version, runs CI, HACS and hassfest checks,
   then creates the release with automatically generated release notes
5. HACS detects new release within hours

### Core Sync

Integration tests in `tests/` are exported to Core. Repository tooling tests belong
in `tests/tooling/` and remain in this repository. The sync workflow uses
`scripts/export_to_core.py`; regression tests check the generated metadata and imports.

1. Commit and push changes
2. Create and push core tag:
   ```bash
   git tag core-v1.2.3
   git push origin core-v1.2.3
   ```
3. GitHub Action syncs to `energy-tracker/core` fork
4. Manually create PR from fork to `home-assistant/core`

## Tag Conventions

| Tag | Target | Creates GitHub Release |
|-----|--------|------------------------|
| `v*` | HACS | ✅ Yes |
| `core-v*` | Core Fork | ❌ No |
