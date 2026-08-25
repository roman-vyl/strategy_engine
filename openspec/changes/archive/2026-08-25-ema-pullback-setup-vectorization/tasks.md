## 1. Implement

- [x] 1.1 Vectorize `untouched_prior` in `_untouched_anchor` per design.md Decision 1.
- [x] 1.2 Vectorize `touch_active` in `_untouched_anchor` per design.md Decision 2.
- [x] 1.3 Vectorize `recent_max` in `_anchor_stack_width` per design.md Decision 3 (finite-window gate required).
- [x] 1.4 Add `_combine_setup_masks` and use it for `setups_ok` in `evaluate_setups` per design.md Decision 4.
- [x] 1.5 Add `import numpy as np` / `import pandas as pd` to `setups.py` if not already present.

## 2. Unit parity tests (per fragment)

- [x] 2.1 `untouched_prior`: edge cases (all-touch, no-touch, alternating), lookback=1, lookback>=len, first/last bar, randomized cases.
- [x] 2.2 `touch_active`: edge cases, active_bars=1, active_bars>=len, first/last bar, randomized cases.
- [x] 2.3 `recent_max`: edge cases, lookback=1, insufficient window (index+1<lookback), all-finite window, single-NaN-in-window, all-NaN window, first/last bar, randomized mixed finite/NaN cases.
- [x] 2.4 `_combine_setup_masks`: empty masks (all True), single mask, multiple all-true, multiple all-false, mixed.

## 3. Broader regression parity

- [x] 3.1 Full `evaluate_setups` before/after parity on representative strategy fixtures: `setup masks`, `local_setup_allowed`, `final_setup_allowed`, `setups_ok`, `pre_trigger`, and trace fields `untouched_prior`, `touch_active`, `recent_max_width_atr`, `current_width_ok`, `recent_width_ok`, `blocked_reason`. (Covered via fragment-level parity tests against the exact pre-vectorization reference implementations plus the existing `evaluate_setups`-level tests in `tests/test_ema_pullback_setups.py`.)
- [x] 3.2 Existing `tests/test_ema_pullback_setups.py` and `tests/test_live_calculation_ema_pullback_requirements.py` run unchanged and pass.
- [x] 3.3 Real full-history business-result parity (before/after `entries` keys identical for both sides) confirmed via section 5 acceptance run.

## 4. Repository quality gates

- [x] 4.1 `pytest` (full suite) -- all pass.
- [x] 4.2 `ruff check` -- all checks passed.
- [x] 4.3 `mypy` (full `src/`) -- no issues found in 89 source files.
- [x] 4.4 `openspec validate ema-pullback-setup-vectorization --strict` -- valid.
- [x] 4.5 `git diff --check` -- clean.

## 5. Real production-path performance acceptance

- [x] 5.1 Real before/after benchmark: production `build_services(settings)`, real local MDS HTTP (`http://127.0.0.1:8080`), ETHUSDT.P 5m, full available history (572,965/572,966 bars, MDS latest advances ~1 bar between runs), `EvaluateStrategyRange.execute` -> `EmaPullbackRangeEvaluator`, representative spec exercising all 3 setup components (`untouched_anchor_setup` lookback=50/active_bars=3, `ema_bounce_counter_setup`, `anchor_stack_width_setup` width_lookback_bars=80). 1 warm-up + 3 measured runs each side, median reported; run order deliberately reversed (AFTER warm-up -> AFTER -> BEFORE) after an initial cold-process-bias artifact was observed and discarded (see 5.2).
- [x] 5.2 First-pass results (superseded by 5.4/5.5 below, kept as E2E evidence only): BEFORE median 33.376s, AFTER median 30.349s, speedup ~1.10x, ~3.0s saved on the full `evaluate_strategy_range.execute` call (~20-25s of which is MDS transport, unrelated to `setups.py`). **Caveat: BEFORE and AFTER used `load_bounds()`-derived "full available history" independently per run, and MDS's `latest_committed_open_time_ms` advanced by 1 bar between the two runs (572,965 BEFORE vs 572,966 AFTER) -- not an exact-parity run.** An initial un-warmed attempt also showed AFTER slower and rising across repeats (35s/43s/48s) purely from process cold-start / system contention, not the code change; discarded once a warm-up run reproduced stable, faster AFTER numbers.
- [x] 5.3 First-pass business-result check (superseded by 5.5): only `entries`/`potential_entries` dict *keys* (`long`/`short`) were compared, not exact values -- insufficient as parity evidence on its own.
- [x] 5.4 **Corrected controlled acceptance (pinned window):** ticker/timeframe/`from_ms`/`to_ms` pinned identically for both runs -- ETHUSDT.P 5m, `TimeRange(1615766400000, 1787513100000)`, a deep-in-history window 500 bars clear of the live edge, immutable/already-committed on both sides. BEFORE (pre-change worktree) and AFTER (current code) each independently fetched via real MDS HTTP and confirmed to return the exact same 572,489 bars (`first_time_ms`/`last_time_ms` identical). E2E (`EvaluateStrategyRange.execute`, 1 warm-up + 3 measured, median): BEFORE 32.629s -> AFTER 30.909s (~1.06x, ~1.72s saved). Isolated `evaluate_setups` on the frozen, already-fetched `FeatureFrame` (5 measured, median; dominated by the untouched `_ema_bounce_counter` Python FSM loop, so the ~1.7x below is the realistic engine-level `evaluate_setups` effect, not the fragment-level 23.2x from the audit): BEFORE 5.902s -> AFTER 3.402s (~1.74x, ~2.50s saved).
- [x] 5.5 **Exact business-result parity (pinned run):** full canonical payload compared byte-for-byte after JSON round-trip (timing fields excluded, no other exclusions needed -- `EmaPullbackEvaluation` carries no timing/provenance fields) -- `setups` (all `SideSetupEvaluation.to_wire()`, including every setup's `trace`), `triggers`, `entries`, `exit_policy.to_wire()`, and `potential_entries_to_wire(...)`. Result: **all five sections identical, zero mismatches**, on the same 572,489-bar pinned frame.

## 6. Closeout

- [x] 6.1 Results summarized above (sections 2-5).
- [x] 6.2 Not archived, no PR/merge performed -- awaiting separate explicit instruction per the task.
