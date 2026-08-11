## 1. Purpose-only fixes (direct canonical edit, not a delta merge)

`openspec archive` ignores `## Purpose` inside a delta for an already-canonical capability — Purpose isn't part of mergeable delta semantics for an existing spec. Apply these by editing `openspec/specs/<capability>/spec.md` directly when this change is applied, not through a delta file:

- [ ] atr-indicator-vertical-slice-v1 — drop stale "parity behavior".
- [ ] ema-pullback-context-bundle-v1 — drop stale "golden parity".
- [ ] ema-pullback-setups-v1 — drop stale "BBB-compatible" framing (Purpose no longer matches its already-renamed requirement).
- [ ] ema-pullback-triggers-v1 — drop stale "golden parity".
- [ ] rsi-indicator-vertical-slice-v1 — drop stale "parity guarantees".

The same direct-edit mechanism also covers Purpose for these 3, alongside their delta-mergeable requirement changes below:

- [ ] ema-indicator-vertical-slice-v1 — drop stale "parity acceptance".
- [ ] ema-pullback-direction-blockers-v1 — drop stale "and parity".
- [ ] strategy-engine-foundation-v1 — drop "before indicator and strategy semantics are ported".

## 2. Apply the requirement deltas

- [ ] Archive merges the 5 delta spec.md files in this change into their canonical specs: `ema-indicator-vertical-slice-v1`, `ema-pullback-feature-plan-v1`, `ema-pullback-direction-blockers-v1`, `strategy-engine-foundation-v1`, `unified-strategy-research-seam-contract-v1`.

## 3. Verify

- [ ] Confirm no production code or test file changed.
- [ ] Run `openspec validate --all --strict`.
