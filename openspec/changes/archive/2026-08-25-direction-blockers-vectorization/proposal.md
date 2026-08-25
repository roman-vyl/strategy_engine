## Why

Real-infra full-history profiling (ETHUSDT.P 5m, ~572,917 bars, `EvaluateStrategyRange.execute` → `EmaPullbackRangeEvaluator`) measured `evaluate_direction_and_blockers` at ~7.66s (~15% of a ~51s full-backtest median), driven by three confirmed Python-level full-frame loops in `direction_blockers.py`: `_rsi_blocker`'s rolling-window scan, `_trend_strength_blocker`'s nested backward peak search, and `evaluate_direction_and_blockers`'s final `all(...)` blocker-combine loop. A follow-up audit built numpy/pandas vectorized candidates for all three and confirmed exact output parity across 29 representative and edge-case scenarios (normal/warmup-NaN, all-pass/all-block, alternating, boundary thresholds, `+inf`/`-inf`, first/last bar, empty/single/multiple blockers, and for `_trend_strength_blocker` specifically every one of `allowed`/`reasons`/`peak_indices`/`bars_since` byte-for-byte), with a synthetic representative-scale benchmark showing ~4.6x-9.0x per-hotspot speedups.

## What Changes

- Replace `_rsi_blocker`'s per-bar Python loop with a numpy `np.isfinite` gate plus a `pandas.Series.rolling(lookback, min_periods=1).max()` rolling-any, matching the existing "RSI memory semantics" requirement (`ema-pullback-direction-blockers-v1`) exactly, including the `min_periods=1`-shaped shortened window at the start.
- Replace `_trend_strength_blocker`'s nested backward-scan loop with a positional "running last qualifying index" numpy computation (`np.maximum.accumulate` over per-bar qualifying-candidate positions, checked against the trailing `peak_lookback_bars` window), preserving the exact reason-priority chain (`indicator_not_ready` → `no_recent_adx_peak` → `peak_too_old` → `current_adx_too_low` → `opposite_di_flip` → allowed) and all four output arrays (`allowed`, `blocked_reason`, `adx_peak_idx`, `bars_since_adx_peak`).
- Replace `evaluate_direction_and_blockers`'s final `all(mask.allowed[index] for mask in blockers) for index in range(...)` combine loop with `np.logical_and.reduce(..., initial=True)` over stacked per-blocker boolean arrays, with an explicit empty-blockers branch returning all-`True` (matching Python's `all([]) == True`) rather than relying on `np.logical_and.reduce`'s behavior on a degenerate empty stack.
- No change to any other function in `direction_blockers.py`, to `evaluate_ema_pullback_frame`'s call graph, or to any other module.
- **BREAKING**: none — purely an internal implementation change; every observable output (`ComponentMask`/`SideDirectionBlockers` fields, `.to_wire()` shape) is unchanged, and the existing `ema-pullback-direction-blockers-v1` capability's documented requirements (RSI memory semantics, trend-strength episode semantics, composition boundary) are preserved exactly, not modified.

## Capabilities

No capability's observable requirements change. `ema-pullback-direction-blockers-v1` already fully documents the semantics this change preserves (RSI memory `min_periods=1` semantics, trend-strength backward-search/reason-priority semantics, AND-composition). `.openspec.yaml` sets `skip_specs: true` accordingly.

## Impact

- Affected code: `src/strategy_engine/strategies/ema_pullback/direction_blockers.py` only (`_rsi_blocker`, `_trend_strength_blocker`, and the final-combine line inside `evaluate_direction_and_blockers`), plus a `numpy` import (already a direct production dependency) and a `pandas` import if not already present in this file.
- Affected tests: the existing direction-blockers test file, extended in place with unit parity cases (per the audit's 29-case matrix) and full-`EmaPullbackEvaluation`/business-result regression; no new test files.
- Unaffected: `FeatureFrame` contracts, strategy spec schema, MDS, `exits.py`, `setups.py`, `serialize_value`, indicator calculation, public/application API.
- Expected performance: real-infra full-history `direction_blockers` cost (currently ~7.66s of a ~51s full-backtest median) materially reduced; exact before/after numbers confirmed by this change's real full-history acceptance run (not the synthetic audit benchmark).
