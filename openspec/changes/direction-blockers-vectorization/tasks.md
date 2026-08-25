## 1. Implement the vectorized replacements

- [x] 1.1 Added `import numpy as np` and `import pandas as pd` to `direction_blockers.py`; removed the now-unused `from math import isfinite`.
- [x] 1.2 `_rsi_blocker` replaced with the `np.isfinite` gate + `pandas.Series.rolling(lookback, min_periods=1).max()` implementation (design.md Decision 1). Signature and return shape unchanged; `trace` keys (`"rsi"`, `"extreme_seen"`) unchanged.
- [x] 1.3 `_trend_strength_blocker` replaced with the running-last-qualifying-index implementation (design.md Decision 2), preserving the exact elif-chain priority order and all four output arrays (`allowed`, `blocked_reason`, `adx_peak_idx`, `bars_since_adx_peak`) and their dtypes.
- [x] 1.4 Final combine replaced with a new private helper `_combine_blocker_masks(blocker_allowed, length)` (`np.logical_and.reduce(..., initial=True)` + explicit empty-blockers branch, design.md Decision 3), called from `evaluate_direction_and_blockers` in place of the original inline `all(...)` loop.
- [x] 1.5 Confirmed by reading the diff (5 hunks: imports, `_rsi_blocker`, `_trend_strength_blocker`, new `_combine_blocker_masks` helper, one-line combine call site): no other function in `direction_blockers.py` touched.

## 2. Unit parity tests (extended `tests/test_ema_pullback_direction_blockers.py` in place)

- [x] 2.1 `_rsi_blocker`: `test_rsi_blocker_normal_and_warmup_nan`, `test_rsi_blocker_all_pass`, `test_rsi_blocker_all_block`, `test_rsi_blocker_alternating`, `test_rsi_blocker_short_side`, `test_rsi_blocker_threshold_equality_is_not_extreme`, `test_rsi_blocker_lookback_one`, `test_rsi_blocker_lookback_larger_than_frame`, `test_rsi_blocker_all_nan`, `test_rsi_blocker_infinities_are_not_extreme`, `test_rsi_blocker_first_last_bar`.
- [x] 2.2 `_trend_strength_blocker`: `test_trend_strength_normal_reference_case`, `test_trend_strength_current_indicator_not_ready`, `test_trend_strength_candidate_nan_inside_lookup_window`, `test_trend_strength_no_recent_peak`, `test_trend_strength_peak_too_old`, `test_trend_strength_min_peak_exact_equality_qualifies`, `test_trend_strength_min_current_exact_boundary`, `test_trend_strength_require_alignment_true_vs_false`, `test_trend_strength_block_flip_true_vs_false`, `test_trend_strength_di_margin`, `test_trend_strength_short_side`, `test_trend_strength_peak_lookback_one`, `test_trend_strength_first_last_bar`, `test_trend_strength_max_since_exact_boundary`, `test_trend_strength_infinities_never_qualify_or_gate_current`, `test_trend_strength_reason_priority_when_multiple_conditions_hold`. Every case asserts `allowed`/`blocked_reason`/`adx_peak_idx`/`bars_since_adx_peak` together where relevant, not `allowed` alone.
- [x] 2.3 Final combine: `test_combine_blocker_masks_empty`, `test_combine_blocker_masks_single_blocker`, `test_combine_blocker_masks_multiple_all_true`, `test_combine_blocker_masks_multiple_all_false`, `test_combine_blocker_masks_mixed`.

## 3. Broader regression parity

- [x] 3.1 Full `pytest` suite passes unchanged (see Group 4).
- [x] 3.2 Representative `evaluate_ema_pullback_frame`/`EmaPullbackEvaluation` regression: covered by the full suite run (no isolated failures in any evaluation-layer test).
- [x] 3.3 Full-history business-result parity: confirmed as part of the Group 5 real-infra acceptance run below (`BUSINESS_RESULTS_IDENTICAL True` before and after, and before matches after exactly).

## 4. Repository quality gates

- [x] 4.1 `pytest` -- all tests pass (full suite incl. 36/36 in the extended direction-blockers file).
- [x] 4.2 `ruff check src tests scripts` -- all checks passed.
- [x] 4.3 `mypy src` -- no issues, 89 source files.
- [x] 4.4 `openspec validate direction-blockers-vectorization --strict` -- valid.
- [x] 4.5 `git diff --check` -- clean.

## 5. Real full-history performance acceptance

- [x] 5.1 Real local infrastructure: production `build_services(settings)`, real local MDS HTTP, real DB, ETHUSDT.P 5m, full available history (bars count recorded per run: 572,935 BEFORE / 572,936 AFTER -- MDS latest advances ~1 bar between runs, negligible), `EvaluateStrategyRange.execute` -> `EmaPullbackRangeEvaluator`.
- [x] 5.2 Before-change (temporary git worktree at pre-implementation commit `3bafe03`) and after-change (current branch): 1 warm-up + 3 measured runs each, recording `_rsi_blocker`, `_trend_strength_blocker`, final-combine (`_combine_blocker_masks`), `evaluate_direction_and_blockers` total, and full backtest total.

  | stage | BEFORE median | AFTER median | speedup | seconds saved |
  |---|---|---|---|---|
  | `_rsi_blocker` | 0.2976s | 0.1413s | ~2.1x | 0.156s |
  | `_trend_strength_blocker` | 6.5456s | 0.5671s | ~11.5x | 5.978s |
  | final combine | 0.7015s | 0.0291s | ~24.1x | 0.672s |
  | `direction_blockers` total | 7.5454s | 1.2191s | ~6.2x | 6.326s |
  | full backtest total | 52.556s | 45.235s | ~1.16x | 7.321s |

- [x] 5.3 Business result identical across all before-runs, all after-runs, and before-vs-after exactly: `entries["long"/"short"]` tail, `exit_policy.signal_exit.long`/`exit_policy.stop_ready.long` tail, and `warnings` all matched.
- [x] 5.4 Recorded above. `direction_blockers` total dropped ~6.2x (7.55s -> 1.22s); full backtest total dropped by ~7.3s absolute (~1.16x) -- consistent with `direction_blockers` being ~14-15% of the full-backtest total, and the remaining time dominated by MDS transport + indicator calculation (untouched by this change, per the prior stage-decomposition audit). Synthetic audit-benchmark numbers were not treated as acceptance proof; this real full-history measurement is.

## 6. Closeout

- [x] 6.1 Changed-file set matches the proposed scope exactly: `src/strategy_engine/strategies/ema_pullback/direction_blockers.py` (production) and `tests/test_ema_pullback_direction_blockers.py` (existing test file, extended in place) -- no other file touched.
- [x] 6.2 Final numbers recorded above (Group 5); parity confirmed (Groups 2-3). **Not archived, no PR/merge performed -- awaiting separate explicit instruction per the task.**
