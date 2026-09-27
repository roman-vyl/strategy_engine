.PHONY: test test-parity lint typecheck release-check verify run build

# tests/parity is architecture-dependent golden-corpus scaffolding built for
# the batch-computation-reuse migration (bit-exact float64 comparison against
# fixtures recorded on arm64; not reproducible bit-for-bit on the x86_64 CI
# runner - see the "temporary migration scaffolding" follow-up issue).
# Excluded from the mandatory CI gate; run explicitly via `make test-parity`.
test:
	python -m pytest --ignore=tests/parity

test-parity:
	python -m pytest tests/parity

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
