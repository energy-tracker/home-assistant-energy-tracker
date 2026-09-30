.PHONY: venv install test lint lint-fix format sync-ruff sync-deps

PYTHON ?= python3

venv:
	$(PYTHON) -m venv .venv

install:
	. .venv/bin/activate && pip install -r requirements-dev.txt -c requirements-dev.lock

sync-deps:
	@echo "🔄 Updating dependencies within requirements and manifest constraints..."
	.venv/bin/python scripts/sync_dependencies.py
	@echo "🔄 Syncing ruff config and Python version from Home Assistant Core..."
	. .venv/bin/activate && python3 scripts/sync_ruff_config.py
	@echo "✅ Dependencies synced and locked"

test:
	. .venv/bin/activate && pytest tests/ -v

coverage:
	. .venv/bin/activate && pytest tests/ --cov=custom_components --cov-report=term-missing --cov-report=html

run-ha:
	. .venv/bin/activate && hass --config .

lint:
	. .venv/bin/activate && ruff check --config ruff.base.toml custom_components tests
	.venv/bin/ruff format --config ruff.base.toml --check custom_components tests
	.venv/bin/ruff check --config ruff.tooling.toml scripts
	.venv/bin/ruff format --config ruff.tooling.toml --check scripts
	. .venv/bin/activate && mypy custom_components
	. .venv/bin/activate && python3 scripts/lint_translations.py

lint-fix:
	.venv/bin/ruff check --config ruff.base.toml --fix custom_components tests
	.venv/bin/ruff check --config ruff.tooling.toml --fix scripts

format:
	.venv/bin/ruff format --config ruff.tooling.toml scripts
	. .venv/bin/activate && ruff format --config ruff.base.toml custom_components tests
	@find custom_components/energy_tracker -name "*.json" | while read file; do \
		python3 -c "import json,sys; d=json.load(open('$$file')); json.dump(d,open('$$file','w'),ensure_ascii=False,indent=2); print('',file=open('$$file','a'))" && echo "✅ $$file"; \
	done

sync-ruff:
	python3 scripts/sync_ruff_config.py
