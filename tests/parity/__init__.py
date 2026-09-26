"""Batch-computation-reuse parity harness and golden corpus (test-only).

OpenSpec change `batch-computation-reuse`, task group 1. Nothing in this
package is imported by production code under `src/`; it drives the real,
unmodified evaluator in-process and records/compares its outputs.

Layout:

- `snapshot.py`   canonical encoding of evaluator outputs (float64 as raw
                  bytes, content-addressed array store) + golden I/O
- `compare.py`    comparison rules (task 1.5)
- `harness.py`    golden recorder: production wiring + recording hooks,
                  real `/range-batch` route body for exact NDJSON bytes
- `corpus.py`     real / synthetic / alias-probe corpus (tasks 1.2-1.4)
- `fetch_market_fixture.py`, `build_real_corpus.py`
                  one-off input builders (MDS slice, Research Service
                  request extraction); their outputs are committed
- `record_golden.py`  (re)writes the golden baseline (task 1.6)
- `test_parity_golden.py`  the parity gate + harness self-check

Re-run the gate:   .venv/bin/python -m pytest tests/parity -q
Re-record golden:  PYTHONPATH=src:tests .venv/bin/python -m parity.record_golden
(re-recording is only legitimate against the pre-change evaluator).
"""
