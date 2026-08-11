## Why

The canonical-hygiene audit found stale Purpose text (leftover "parity"/"golden parity" wording after the parity oracle was retired), one requirement that defines correctness only via the deleted `legacy_source` oracle, and bootstrap-era "before porting"/"later derives" phrasing describing migration events long since completed.

## What Changes

- Purpose-only fixes for 5 capabilities via direct canonical edit at apply time — Purpose isn't part of mergeable delta semantics for an existing capability (see tasks.md).
- `ema-indicator-vertical-slice-v1`: durable fail-closed wording, drop change-scoped phrasing, Purpose fix.
- `ema-pullback-feature-plan-v1`: rename+replace the BBB-oracle-dependent requirement with the deterministic invariant native tests already pin.
- `ema-pullback-direction-blockers-v1`: rename+replace "Blocker parity" with self-contained behavior, referencing (not duplicating) sibling requirements.
- `strategy-engine-foundation-v1`: drop bootstrap-era framing from 4 requirements and Purpose; every architecture boundary stays intact.
- `unified-strategy-research-seam-contract-v1`: reword "Single physical seam" as a present-tense invariant, not a migration-mapping record.

No production code, tests, or capability boundaries change.

## Impact

`openspec/specs/` only.
