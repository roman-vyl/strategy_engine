## 1. Remove the copied BBB source and parity tooling

- [ ] 1.1 Delete `legacy_source/` and its provenance/copy scripts (`scripts/copy_legacy_source.py`, `scripts/verify_legacy_source.py`).
- [ ] 1.2 Delete the parity manifest and gate script (`parity/`, `scripts/run_semantic_parity_gate.py`).

## 2. Remove BBB golden/parity tests

- [ ] 2.1 Delete test files whose sole purpose is BBB golden/parity comparison (e.g. `tests/test_*_bbb_golden_parity.py`, `tests/test_*_bbb_parity.py`, `tests/test_semantic_parity_gate_manifest.py`).
- [ ] 2.2 In mixed test files that combine native and parity coverage, remove only the parity-comparison fragments and keep native tests intact.
- [ ] 2.3 Update `tests/test_architecture.py` so its legacy/BBB import boundary checks no longer reference `legacy_source` paths that stop existing.

## 3. Clean operational docs

- [ ] 3.1 Remove legacy-parity-gate instructions and the `legacy_source/` provenance section from `README.md` and any other operational docs that document running the retired parity gate.

## 4. Verify

- [ ] 4.1 Run the full native test suite and confirm it passes with `legacy_source/`, `parity/`, and the removed tests gone.
- [ ] 4.2 Run `openspec validate --strict` for the archived spec deltas.
