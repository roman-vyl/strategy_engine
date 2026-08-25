## Why

Four remaining per-bar Python loops in `setups.py` are safely vectorizable via
the same rolling-window / finite-gate / AND-reduce techniques already shipped
and accepted in `exit-policy-profile-select-vectorization` and
`direction-blockers-vectorization`. A 4-fragment parity audit (edge cases +
randomized cases, 0 mismatches) plus a synthetic ~48.8k-bar microbench
confirmed all four are stateless, exactly vectorizable, and the costliest
fragment (`recent_max`) is ~23x faster in isolation.

## What Changes

- `_untouched_anchor`: vectorize `untouched_prior` (trailing "not any touch in
  the strictly-prior, non-shortened window" check) via `shift(1)` +
  `rolling(lookback, min_periods=lookback).max()`.
- `_untouched_anchor`: vectorize `touch_active` (trailing "any first_touch in
  a window clipped at the series start" check) via
  `rolling(active_bars, min_periods=1).max()`.
- `_anchor_stack_width`: vectorize `recent_max` (trailing rolling max of
  `width_atr`, full lookback required, NaN if any element in the window is
  non-finite) via `rolling(lookback).max()` combined with a separate
  `rolling(lookback).min()` all-finite gate.
- `evaluate_setups`: vectorize the `setups_ok` AND-combine loop using the
  same `np.logical_and.reduce(..., initial=True)` pattern already in
  production for `direction_blockers._combine_blocker_masks`, preserving the
  empty-masks-means-all-True semantics.

`_ema_bounce_counter` (a stateful sequential FSM) is explicitly out of scope.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — this is a pure internal vectorization, no observable behavior change.
`skip_specs: true` is set in `.openspec.yaml`; the existing
`ema-pullback-setups-v1` spec already documents the semantics being
preserved.

## Impact

- Code: `src/strategy_engine/strategies/ema_pullback/setups.py` only
  (the four named fragments).
- Tests: `tests/test_ema_pullback_setups.py` (new parity tests), plus running
  existing regression/integration suites unchanged.
- No change to `FeatureFrame`, public API, strategy spec schema, MDS,
  `_ema_bounce_counter`, `_apply_gate`, or `pre_trigger` computation.
- Expected performance: real production-path effect to be measured after
  apply via before/after benchmark on `evaluate_setups`; the 23.2x figure
  from the audit is for the `recent_max` fragment in isolation only, not a
  claim about `evaluate_setups` or the engine as a whole.
