## Why

Strategy Engine's migration from BBB is complete. The copied BBB source and semantic parity oracle were a migration-era acceptance scaffold, not a permanent requirement, and native Engine tests already cover the same behavior independently.

## What Changes

Retire the `ema-pullback-semantic-parity-gate-v1` capability and every BBB copied-source/golden-parity requirement from canonical truth via the spec deltas in this change, without changing production semantics and without introducing a replacement parity gate. **BREAKING**: the BBB parity gate is no longer a canonical acceptance requirement. See `specs/` for the exact REMOVED/RENAMED/MODIFIED requirements. Deleting `legacy_source/`, parity tooling, and BBB test files is deferred to `tasks.md` and not performed by this proposal.

## Impact

Canonical specs under `openspec/specs/` only. No production code, runtime behavior, Docker, or other active OpenSpec changes are affected.
