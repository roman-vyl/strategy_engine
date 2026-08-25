## 1. Implement the vectorized selector

- [x] 1.1 Add `import numpy as np` to `src/strategy_engine/strategies/ema_pullback/exits.py`.
- [x] 1.2 Add `_PROFILE_CODE = {name: i for i, name in enumerate(_PROFILE_ORDER)}` next to `_PROFILE_ORDER`.
- [x] 1.3 Replace `_select`'s body with the numpy stacked-matrix + integer-code positional gather (design.md Decision 1). Signature unchanged.
- [x] 1.4 Replace `_select_bool`'s body with the same gather, `dtype=bool` throughout. Signature unchanged.
- [x] 1.5 Confirmed by reading: all 12 existing call sites in `evaluate_exit_policy` (lines 500-520) are byte-for-byte unchanged.

## 2. Parity tests (extended `tests/test_ema_pullback_exits.py` in place)

- [x] 2.1 `test_select_all_neutral_profile`
- [x] 2.2 `test_select_mixed_profile`
- [x] 2.3 `test_select_switches_every_bar`
- [x] 2.4 `test_select_nan_present_in_all_three_profile_series`
- [x] 2.5 `test_select_nan_selected_vs_unselected_positional_behavior`
- [x] 2.6 `test_select_bool_selection`
- [x] 2.7 `test_select_preserves_exact_index_including_non_default`
- [x] 2.8 `test_select_preserves_exact_dtype`
- [x] 2.9 `test_select_unknown_profile_name_raises_key_error` / `test_select_bool_unknown_profile_name_raises_key_error`

## 3. Broader regression parity

- [x] 3.1 Full `ExitPolicyEvaluation` parity: all pre-existing exit-policy tests (`test_exit_policy_returns_signal_and_distance_outputs`, `test_raw_distances_do_not_change_exit_policy_wire_output`, `test_profile_selection_uses_side_relative_context_result`, `test_profile_distance_selection_preserves_the_same_minimum_raw_distance`, `test_configured_stop_series_entirely_null_is_not_ready`, `test_configured_take_series_entirely_null_is_not_ready`, `test_absent_protection_kind_does_not_block_readiness`, `test_partially_valid_configured_series_preserves_per_bar_readiness`, `test_atr_raw_distance_is_applied_to_anchor_when_close_differs`, `test_unknown_exit_component_is_rejected`) pass unchanged -- these already exercise mixed-profile selection (`profile_long=("aligned","countertrend","aligned","countertrend")` etc.) end-to-end through `evaluate_exit_policy`, not just the new direct unit tests.
- [x] 3.2 Representative `evaluate_ema_pullback_frame`/`EmaPullbackEvaluation` regression: `pytest -k "evaluation or ema_pullback_frame"` passes unchanged.

## 4. Repository quality gates

- [x] 4.1 `pytest` -- all tests pass (full suite, 20/20 in the extended exit-policy file).
- [x] 4.2 `ruff check src tests scripts` -- all checks passed.
- [x] 4.3 `mypy src` -- no issues, 89 source files.
- [x] 4.4 `git diff --check` -- clean.

## 5. Real performance acceptance

- [x] 5.1 Real local infrastructure: production `build_services(settings)`, real local MDS HTTP, real DB, ETHUSDT.P 5m, same scenario as the prior audit/benchmarks: `source_plan_bar_open_time_ms=1,786,982,100,000`, `entry_bar_open_time_ms=1,786,983,000,000`, `target_bar_open_time_ms=1,787,587,800,000` (all still within current MDS bounds, confirmed before running).
- [x] 5.2 Before-change (temporary git worktree at pre-implementation commit `d19a4b0`): 1 warm-up + 3 measured `EvaluateOpenTradeProjection.execute` calls. `evaluate_exit_policy` wall-clock: [3.944, 3.939, 3.975]s, median **3.944s**. `open_trade_total`: [7.474, 18.783, 7.484]s (run 2 an isolated network-jitter outlier -- MDS HTTP variance, unrelated to this change), median **7.484s**.
- [x] 5.3 After-change (current branch): same scenario/machine/DB/MDS. `evaluate_exit_policy` wall-clock: [0.2747, 0.2798, 0.2827]s, median **0.2798s**. `open_trade_total`: [3.760, 3.836, 3.815]s, median **3.815s**.
- [x] 5.4 All before-runs and all after-runs produced an identical business result, and before matches after exactly: `('1869.97', '1946.29', False, None, 'proven', 2017, '0.33594147149303244', '0.012583000110055509')`.
- [x] 5.5 Recorded: `evaluate_exit_policy` 3.944s -> 0.2798s median (~14.1x; the residual ~0.28s matches `_frame_dataframe`/`_optional_floats`/`_signal_rule`/`_distance`/`_or`/`_min` costs identified as untouched by this change in the prior audit). Full OpenTrade total 7.484s -> 3.815s median (-3.669s, matching the `_select`/`_select_bool` reduction almost exactly), consistent with the prior audit's floor estimate (~4.16s after removing this hotspot alone).

## 6. Closeout

- [x] 6.1 Changed-file set matches the proposed scope exactly: `src/strategy_engine/strategies/ema_pullback/exits.py` (production) and `tests/test_ema_pullback_exits.py` (existing test file, extended in place) -- no other file touched.
- [x] 6.2 Final numbers recorded above (Group 5); parity confirmed (Groups 2-3). Ready to archive.

**Status: all tasks complete. Ready to archive.**
