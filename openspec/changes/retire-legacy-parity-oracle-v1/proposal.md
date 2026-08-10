## Why

Strategy Engine's migration from BBB is complete. The copied BBB source under `legacy_source/` and the semantic parity oracle (`parity/`, `scripts/run_semantic_parity_gate.py`, BBB golden/parity tests) are no longer the acceptance mechanism for production semantics — they were a migration-era scaffold, not a permanent requirement. Production semantics do not change; native Engine tests already cover the same behavior independently and become the sole verification layer. Canonical specs must stop requiring the retired oracle before its removal can be implemented.

## What Changes

- Retire capability `ema-pullback-semantic-parity-gate-v1` from canonical truth: **BREAKING** — the BBB copied-source parity gate ceases to be a canonical acceptance requirement. No replacement parity gate is introduced.
- Remove "Golden parity" / "BBB parity" requirements from indicator and EMA Pullback capabilities where the requirement existed solely to mandate running the copied BBB source as a comparison oracle.
- Modify requirements that describe real production semantics but currently phrase their acceptance criterion as "match the copied BBB implementation" — reword to describe the retained production behavior without the copied-source comparison obligation.
- Modify architecture-boundary requirements that reference the parity oracle mechanism (loading copied BBB code as a "parity oracle", forward references to a future "golden parity against BBB" follow-up) to drop the retired mechanism while keeping the "no BBB/legacy runtime dependency in production" architectural guarantee.
- This proposal is spec-only. Deleting `legacy_source/`, the parity manifest/scripts, BBB golden/parity test files, parity fragments inside mixed test files, and legacy-parity instructions from README/operational docs is deferred to the apply stage of this change (see `tasks.md`) and is **not** performed now.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `ema-pullback-semantic-parity-gate-v1`: capability retired — all 6 requirements REMOVED; the capability is no longer canonical truth.
- `atr-indicator-vertical-slice-v1`: REMOVE "Golden parity" (copied-BBB comparison test requirement).
- `ema-indicator-vertical-slice-v1`: REMOVE "Golden parity" (copied-BBB comparison test requirement).
- `rsi-indicator-vertical-slice-v1`: REMOVE "Golden parity" (copied-BBB comparison test requirement).
- `ema-pullback-context-bundle-v1`: REMOVE "Golden parity" (copied-BBB comparison test requirement).
- `ema-pullback-direction-blockers-v1`: REMOVE "BBB parity" (copied-BBB comparison test requirement).
- `ema-pullback-triggers-v1`: REMOVE "Golden parity"; MODIFY "Side symmetry" to drop the copied-BBB comparison clause while keeping the long/short mirroring guarantee.
- `adx-dmi-indicator-vertical-slice-v1`: MODIFY "Coupled calculation" to drop the copied-BBB bar-for-bar comparison clause while keeping the shared-calculation-once guarantee.
- `ema-pullback-setups-v1`: MODIFY "Legacy setup parity", "Stateful bounce semantics", and "Evidence" to drop copied-BBB comparison/diagnostic language while keeping the deterministic, bar-aligned production behavior each requirement defines.
- `ema-pullback-feature-plan-v1`: MODIFY "No legacy production imports" to drop the retired "golden tests may load copied BBB code as parity oracle" allowance while keeping the production import boundary.
- `strategy-engine-foundation-v1`: MODIFY "No semantic overclaim" to drop the forward reference to a future "golden parity against BBB" follow-up.

## Impact

- Canonical specs under `openspec/specs/` (11 capabilities listed above).
- Future apply stage only: `legacy_source/`, `parity/`, `scripts/run_semantic_parity_gate.py`, `scripts/verify_legacy_source.py`, `scripts/copy_legacy_source.py`, BBB golden/parity test files, parity fragments inside mixed test files, README/operational-doc legacy-parity instructions.
- No production code, runtime behavior, Docker, or other active OpenSpec changes are affected.
