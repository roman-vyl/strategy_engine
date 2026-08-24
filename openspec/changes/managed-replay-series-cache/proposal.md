## Why

Real local infrastructure profiling of `EvaluateOpenTradeProjection` (production `build_services` composition, real MDS HTTP, real DB, ETHUSDT.P 5m, a ~7-day open trade) measured a ~30s median total, of which managed replay (`_evaluate_managed_replay_core` in `strategies/ema_pullback/managed.py`) accounts for ~22s (~70%+). A source audit confirmed the dominant cause: `_series(frame, output_id)` re-materializes the entire feature-series column (full-length tuple, `float()`-converted from decimal text) on every call, and it is called from inside the per-bar managed-replay loop (via `_feature_value` for phase/stop-management ATR/ADX conditions, and directly for `rsi_signal_exit`/`ema_cross_loss_exit` runtime-exit checks). The same `output_id` is re-materialized up to once per bar per rule that reads it, instead of once per replay execution. This is a confirmed, isolated performance defect, not a design-level bottleneck in the trading state machine itself.

## What Changes

- Add a lazy, per-replay-execution feature-series cache inside `_evaluate_managed_replay_core` (`managed.py`): `output_id -> tuple[float | None, ...]`, populated on first access and reused for the remainder of that single replay call. No persistent, cross-request, or global cache.
- Route every existing per-bar feature-series access point (`_feature_value`, and the two direct `_series()` calls in `_runtime_signal`'s `rsi_signal_exit`/`ema_cross_loss_exit` branches) through this cache instead of calling `_series()` (full re-materialization) directly.
- No change to the trading state machine, rule evaluation order, or any computed value. This is a pure feature-access-cost optimization behind the existing internal helpers.
- The shared managed-replay core (`_evaluate_managed_replay_core`) has exactly two real callers today (confirmed by call-graph audit): the production live OpenTrade path (`evaluate_start_after_entry_managed_projection`, called from `EmaPullbackOpenTradeProjectionAdapter.evaluate`) and the single-trade managed-replay HTTP endpoint (`evaluate_managed_replay`, wired to `POST /strategy-evaluations/managed-replay` via `EvaluateManagedReplay`, the Research/Workbench-facing managed-replay path). Both benefit automatically because the cache lives inside the one shared core, not a path-specific fast path. The bulk Research/Backtest range evaluator (`EmaPullbackRangeEvaluator`/`evaluate_range.py`) does **not** call this core at all (it explicitly rejects `exit_management.mode="managed"` and redirects callers to the managed-replay endpoint instead) — this change does **not** claim or measure any effect on that path.

## Capabilities

No capability's observable requirements change. This is an internal, behavior-preserving performance optimization: every existing OpenSpec-described behavior of managed replay (state transitions, event ordering/content, bar decisions, desired stop/take, close signal) must remain byte-for-byte identical before and after. `.openspec.yaml` sets `skip_specs: true` accordingly — no delta spec files are part of this change.

## Impact

- Affected code: `src/strategy_engine/strategies/ema_pullback/managed.py` only (expected). No other production file is expected to require changes.
- Affected tests: existing managed-replay/OpenTrade test files (`tests/test_ema_pullback_managed.py`, `tests/test_ema_pullback_start_after_entry_managed.py`, `tests/test_ema_pullback_managed_api.py`, `tests/test_open_trade_projection_composition.py`) may gain parity/regression assertions; no new test files expected unless a genuine gap is found.
- Unaffected: bounded-history planning (`live_calculation/`), MDS client, indicator calculation, `evaluate_ema_pullback_frame`, `FeatureFrame` contract, HTTP API, strategy spec schema, Research/Backtest bulk range evaluation, Runtime/ABI contracts.
- **BREAKING**: none.
