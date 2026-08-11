## 1. Remove the copied BBB source and parity tooling

- [x] 1.1 Delete `legacy_source/` and its provenance/copy scripts (`scripts/copy_legacy_source.py`, `scripts/verify_legacy_source.py`).
- [x] 1.2 Delete the parity manifest and gate script (`parity/`, `scripts/run_semantic_parity_gate.py`).

## 2. Remove BBB golden/parity tests

- [x] 2.1 Delete test files whose sole purpose is BBB golden/parity comparison (e.g. `tests/test_*_bbb_golden_parity.py`, `tests/test_*_bbb_parity.py`, `tests/test_semantic_parity_gate_manifest.py`).
- [x] 2.2 In mixed test files that combine native and parity coverage, remove only the parity-comparison fragments and keep native tests intact.
- [x] 2.3 Leave `tests/test_architecture.py` unchanged — its production-import guard against `legacy_source`/BBB is a permanent architecture check, not parity tooling.

## 3. Clean operational docs

- [x] 3.1 Remove legacy-parity-gate instructions and the `legacy_source/` provenance section from `README.md` and any other operational docs that document running the retired parity gate.

## 4. Archive

- [x] 4.1 When archiving this change, confirm `openspec/specs/ema-pullback-semantic-parity-gate-v1/` no longer exists afterward. If the archive step leaves an empty spec file for that capability, delete the directory as part of the archive commit.

## 5. Verify

- [x] 5.1 Run the full native test suite and confirm it passes with `legacy_source/`, `parity/`, and the removed tests gone.
- [x] 5.2 Run `openspec validate --strict` for the archived spec deltas.
