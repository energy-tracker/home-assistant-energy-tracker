.PHONY: venv install test lint format sync-ruff sync-deps

PYTHON ?= python3

venv:
	$(PYTHON) -m venv .venv

install:
	. .venv/bin/activate && pip install -r requirements-dev.txt -c requirements-dev.lock

sync-deps:
	@echo "🔄 Syncing pytest-homeassistant-custom-component to latest version..."
	. .venv/bin/activate && pip install --upgrade pytest-homeassistant-custom-component
	@echo "🔄 Upgrading dev tools (ruff, mypy)..."
	. .venv/bin/activate && pip install --upgrade ruff mypy energy-tracker-api
	@echo "🔄 Syncing ruff config and Python version from Home Assistant Core..."
	. .venv/bin/activate && python3 scripts/sync_ruff_config.py
	@echo "🔄 Writing locked versions to requirements-dev.lock..."
	. .venv/bin/activate && pip freeze | grep -iE '^(pytest-homeassistant-custom-component|homeassistant|ruff|mypy|pytest|pytest-asyncio|pytest-cov|energy-tracker-api)=' > requirements-dev.lock
	@echo "✅ Dependencies synced and locked"

test:
	. .venv/bin/activate && pytest tests/ -v

coverage:
	. .venv/bin/activate && pytest tests/ --cov=custom_components --cov-report=term-missing --cov-report=html

run-ha:
	. .venv/bin/activate && hass --config .

lint:
	. .venv/bin/activate && ruff check --config ruff.base.toml --fix custom_components tests
	. .venv/bin/activate && mypy custom_components
	. .venv/bin/activate && python3 scripts/lint_translations.py

format:
	. .venv/bin/activate && ruff format --config ruff.base.toml custom_components tests
	@find custom_components/energy_tracker -name "*.json" | while read file; do \
		python3 -c "import json,sys; d=json.load(open('$$file')); json.dump(d,open('$$file','w'),ensure_ascii=False,indent=2); print('',file=open('$$file','a'))" && echo "✅ $$file"; \
	done

sync-ruff:
	python3 scripts/sync_ruff_config.py
