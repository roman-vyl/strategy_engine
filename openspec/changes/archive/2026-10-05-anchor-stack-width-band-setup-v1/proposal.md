## Why

`anchor_stack_width_setup` combines two conditions: the current stack width must reach a minimum, and the largest width over a
trailing window must reach a second minimum. It has no upper bound, and its current-bar condition cannot be used without the
trailing-window condition. A setup that admits a bar only when the current stack width lies inside a band `[min, max]` cannot be
expressed with it. That condition is a basic building block, so it is added once as a separate, stateless setup component. The
existing component stays exactly as it is.

## What Changes

- One new setup component `anchor_stack_width_band_setup` with params:
  - `atr_timeframe` (optional, default `base`) and `atr_period` (optional, default 14): the ATR feature, with the same meaning and
    defaults as in `anchor_stack_width_setup`;
  - `min_width_atr` (required): finite number, `> 0`;
  - `max_width_atr` (optional): finite number, `>= min_width_atr`. When absent, the band has no upper bound.
  - Any other key is rejected.
- Semantics. On every base bar:
  `width_atr = |fast - slow| / atr`, where `fast` and `slow` are the anchor-stack EMAs and `atr` is the planned ATR column.
  The setup is True iff `min_width_atr <= width_atr` and, when `max_width_atr` is present, `width_atr <= max_width_atr`.
  Both bounds are inclusive.
- The component reads the current bar only: no lookback, no trailing maximum, no hold window, no state.
- Readiness: False where `fast`, `slow` or `atr` is missing or non-finite, or `atr <= 0`.
- Side: side-free.
- It is a supported setup in every place where `anchor_stack_width_setup` is: top-level `setups` (with or without
  `context_consumption`) and a `setup` child of `composite_setup`.
- Planning: no new indicator. It uses the anchor-stack `fast` and `slow` columns and one ATR feature planned by the existing
  `add_atr`, deduplicated with every other consumer of the same ATR.
- Identity: two new node families, a side-free, threshold-free `width` node and the threshold `local` node over it.
  Candidates that differ only in the bounds share the `width` node.
- Live history: an explicit zero-additional-history entry (the indicator warm-up is counted from the plan).
- Nothing changes for specs that do not use `anchor_stack_width_band_setup`: same plan, `plan_hash`, node identities, compute
  counts and outputs. `anchor_stack_width_setup` keeps its parameters, defaults, identity, trace and code path.

## Impact

- `ema-pullback-setups-v1`: MODIFIED `Supported setup determinism`, `Composite setup is a supported setup`;
  ADDED `Anchor stack width band setup`.
- `ema-pullback-composite-setup-v1`: MODIFIED `Children` (the new component is an allowed `setup` child).
- `ema-pullback-feature-plan-v1`: ADDED `Anchor stack width band setup features`.
- `live-calculation-window-planning`: ADDED `History policy for the anchor stack width band setup`.
- `batch-computation-reuse`: ADDED `Identity of the anchor stack width band setup`,
  `No compute regression without the anchor stack width band setup`.
- Code: `raw_spec_identity.py` (`SETUP_SUPPORTED`), `composite_spec.py` (`SEMANTIC_SETUP_CHILDREN`), `setups.py` (compute and
  resolve), `feature_plan.py` (`plan_setup_columns`), `live_calculation_requirements.py` (`_semantic_setup`),
  `static_semantics.py` (parameter validation), `composer_catalog.py` (one new `ComponentSchema`).
- Not modified: `anchor_stack_width_setup`, `pre-entry-predicates-v1`, `ema-pullback-composite-phase-condition-v1`,
  `historical-managed-projection-v1`, `live-entry-projection-v1`, the wire contract.

## Verification

- Unit tests: inclusive lower and upper bounds (a bar exactly on `min` and exactly on `max` is True), no upper bound, `min == max`,
  readiness (non-finite `fast`/`slow`/`atr`, `atr <= 0`), ATR on base and on a higher timeframe, side-freeness, determinism.
- Static validation: missing `min_width_atr`, non-numeric, non-finite or non-positive bounds, `max_width_atr < min_width_atr`,
  unknown keys; acceptance at top level, with `context_consumption`, and as a `composite_setup` child.
- Equivalence of the width formula: with the same ATR, `width_atr` of the new component equals `current_width_atr` of
  `anchor_stack_width_setup` on every bar where both are finite. The masks of the two components are not required to agree.
- Identity and memo: bounds-only candidates share one `width` computation; zero `unforeseen_consumptions`; memoized and
  non-memoized outputs are bit-identical.
- Regression: existing suites that pin `plan_hash`, node identities, compute counts and outputs pass unchanged.
- Gate: ruff, mypy, the full suite, `openspec validate anchor-stack-width-band-setup-v1 --strict`.
