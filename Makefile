.PHONY: test lint typecheck verify run build

test:
	python -m pytest

lint:
	ruff check src tests

typecheck:
	mypy src

verify: lint typecheck test

run:
	uvicorn strategy_engine.adapters.http.app:create_app --factory --host 127.0.0.1 --port 8090

build:
	python -m build
