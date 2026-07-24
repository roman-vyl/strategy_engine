.PHONY: test lint typecheck release-check verify run build

test:
	python -m pytest

lint:
	ruff check src tests scripts

typecheck:
	mypy src

release-check:
	python scripts/verify_release_archive.py .

verify: lint typecheck test release-check

run:
	uvicorn strategy_engine.adapters.http.app:create_app --factory --host 127.0.0.1 --port 8090

build:
	python -m build
