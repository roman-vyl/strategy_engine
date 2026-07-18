PYTHON ?= python

.PHONY: check-python test lint typecheck verify run build

check-python:
	@$(PYTHON) scripts/check_python_version.py

test: check-python
	$(PYTHON) -m pytest

lint: check-python
	$(PYTHON) -m ruff check src tests

typecheck: check-python
	$(PYTHON) -m mypy src

verify: lint typecheck test

run: check-python
	$(PYTHON) -m uvicorn strategy_engine.adapters.http.app:create_app \
		--factory --host 127.0.0.1 --port 8090

build: check-python
	$(PYTHON) -m build
