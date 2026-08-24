## 1. Regression / parity baseline

- [x] 1.1 Capture a deterministic before-change semantic baseline on current `main`: for a fixed, existing test fixture (or a new small one if none reasonably covers a multi-rule managed replay) that exercises phase transitions, at least one ATR-based stop/phase condition, and at least one runtime exit reading a feature series (e.g. `ema_cross_loss_exit` and/or `rsi_signal_exit`), record: final `ManagedTradeState` (every field), the full ordered `events` tuple, the full ordered `bars` tuple, and (for the OpenTrade entry point specifically) `StartAfterEntryManagedProjection.desired_stop_price`/`desired_take_price`. Done by extending the existing `tests/test_ema_pullback_managed.py` fixture (`lock_profit_stop`, ATR-based) with a new `ema_cross_loss_exit` runtime rule (fast leg = real `ema_close_base_2`, slow leg = a period nothing produces) and running it against pre-change code; full state/events/bars captured (see Group 4/5 results below).
- [x] 1.2 Confirm via a lightweight call-counting instrumentation (test-local monkeypatch of `_series`) how many times `_series()` is actually invoked for the same `output_id` within one replay call on this fixture. Before-change counts: `ema_close_base_2`=6, `ema_close_base_999`=6, `atr_close_base_2`=4 (6 replay bars; matches the confirmed per-bar re-materialization pattern).
- [x] 1.3 Capture the same before-change baseline for at least one `output_id` that is *not* present in `frame.series`. Confirmed: `_series()` returns an all-`None` tuple the length of `frame.time_ms` (6 elements), not an exception -- both via the naturally-occurring `ema_close_base_999` case (planned but absent from the frame) and a direct call with an arbitrary unknown `output_id`.

## 2. Per-replay lazy series cache

- [x] 2.1 Inside `_evaluate_managed_replay_core`, create a local cache (`SeriesCache = dict[str, tuple[float | None, ...]]`) at the start of the function, scoped to that single call.
- [x] 2.2 Add `_cached_series(cache, frame, output_id)`: returns the cached tuple if present, otherwise calls `_series(frame, output_id)` once, stores it, returns it. `_series()` itself is unchanged.

## 3. Wire cache through existing managed helpers

- [x] 3.1 `_feature_value` now takes `cache: SeriesCache` and calls `_cached_series` instead of `_series`; both its callers (`_phase_met`'s `mfe_atr`/`adx_di_threshold` branches, and the `break_even_stop`/`lock_profit_stop` ATR branches in `_evaluate_managed_replay_core`) pass the per-call `series_cache`.
- [x] 3.2 `_runtime_signal` now takes `series_cache: SeriesCache` and routes its `rsi_signal_exit` and `ema_cross_loss_exit` (both fast and slow leg) `_series()` calls through `_cached_series`.
- [x] 3.3 Confirmed by reading: the only direct call to `_series()` left in `managed.py` is inside `_cached_series` itself; all four original call sites (`_feature_value`, `rsi_signal_exit`, `ema_cross_loss_exit` x2) now go through the cache.

## 4. Semantic parity tests

- [x] 4.1 Re-ran the Group 1 fixture after the Group 2/3 change: final `ManagedTradeState`, all 8 `ManagedPolicyEvent`s, all 6 `ManagedBarDecision`s, byte-for-byte identical to the Group 1.1 baseline (verified via direct before/after script comparison of the printed representations).
- [x] 4.2 New permanent test `tests/test_ema_pullback_managed.py::test_series_materialized_at_most_once_per_output_id_per_replay` asserts exactly 1 call per `output_id` (`atr_close_base_2`, `ema_close_base_2`, `ema_close_base_999`) across the 6-bar replay -- down from the Group 1.2 baseline of 4-6. The call-counting technique itself is test-local (`monkeypatch.setattr`), not left behind as production code.
- [x] 4.3 New permanent test `tests/test_ema_pullback_managed.py::test_series_missing_output_id_returns_none_tuple_matching_frame_length` confirms the missing-`output_id` path still returns an all-`None`, frame-length tuple.
- [x] 4.4 Full existing managed-replay/OpenTrade test suite passes unchanged (`tests/test_ema_pullback_managed.py`, `tests/test_ema_pullback_start_after_entry_managed.py`, `tests/test_ema_pullback_managed_api.py`, `tests/test_open_trade_projection_composition.py`) -- part of the full `pytest` run (all tests green, see Group 6).
- [x] 4.5 Confirmed via the Group 5 real-infra run: `OpenTradeProjectionResult` (desired_protection stop/take, close_signal, diagnostics.phase/max_phase_reached/bars_in_trade/mfe_pct/mae_pct) identical before and after -- see Group 5 business-result tuple below.

## 5. Real performance acceptance

- [x] 5.1 Real local infrastructure: production `build_services(settings)` composition, real local MDS HTTP (`http://127.0.0.1:8080`), real DB, ETHUSDT.P 5m, the identical scenario used for the original `bounded-live-calculation-window` Group 7 profile: `source_plan_bar_open_time_ms=1,786,982,100,000`, `entry_bar_open_time_ms=1,786,983,000,000`, `target_bar_open_time_ms=1,787,587,800,000` (all still within current MDS bounds, confirmed before running).
- [x] 5.2 Before-change (temporary git worktree at pre-cache commit `cb3645e`): 1 warm-up + 3 measured `EvaluateOpenTradeProjection.execute` calls. `managed_replay` wall-clock: [20.967, 21.042, 20.951]s, median **20.967s**. `open_trade_total`: [28.319, 28.785, 28.646]s, median **28.646s**.
- [x] 5.3 After-change (current branch): same scenario/machine/DB/MDS, same 1 warm-up + 3 measured calls. `managed_replay` wall-clock: [0.0242, 0.0239, 0.0241]s, median **0.0241s**. `open_trade_total`: [21.768, 7.559, 7.588]s, median **7.588s** (run 1 an outlier, consistent with a one-time cold-start cost elsewhere in the composition -- runs 2/3 stable at ~7.56-7.59s).
- [x] 5.4 All before-runs and all after-runs produced an identical business result, and before matches after exactly: `('1869.97', '1946.29', False, None, None, None, 'proven', 'proven', 2017, '0.33594147149303244', '0.012583000110055509')` (stop_price, take_price, close_signal.active/reason/component_id/layer, phase, max_phase_reached, bars_in_trade, mfe_pct, mae_pct).
- [x] 5.5 Accepted: (a) repeated full-series materialization eliminated (Group 4.2, confirmed 1 call per `output_id`); (b) managed-replay latency materially decreased -- 20.967s -> 0.0241s median (~870x), far exceeding the "single-digit seconds" reasonable-expectation framing in design.md; (c) full OpenTrade latency did not regress -- 28.646s -> 7.588s median, consistent with the ~8-10s floor predicted from the standalone MDS/indicator-evaluation profile once managed replay stopped dominating.

## 6. Closeout

- [x] 6.1 Repository quality gates: `pytest` (all tests pass), `ruff check src tests scripts` (all checks passed), `mypy src` (no issues, 89 source files), `openspec validate managed-replay-series-cache --strict` (valid), `git diff --check` (clean).
- [x] 6.2 Changed-file set matches design.md's expected scope exactly: `src/strategy_engine/strategies/ema_pullback/managed.py` (production) and `tests/test_ema_pullback_managed.py` (existing test file, extended in place) -- no other production or test file touched, no new files.
- [x] 6.3 Final numbers recorded above (Group 4/5). Ready to archive per the repository's standard OpenSpec archive workflow.

**Status: all tasks complete. Ready to archive.**
