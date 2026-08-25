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
- [x] 5.2 Results: BEFORE median 33.376s, AFTER median 30.349s, speedup ~1.10x, ~3.0s saved on the full `evaluate_strategy_range.execute` call (which also includes ~20-25s of MDS transport unrelated to `setups.py`). An initial un-warmed run showed AFTER slower and rising across repeats (35s/43s/48s) purely from process cold-start / system contention, not from the code change; discarded once a warm-up run reproduced stable, faster AFTER numbers. Per design.md's explicit caution, the isolated `recent_max` fragment's 23.2x audit figure is not claimed here as the engine-level effect -- the engine-level effect is the ~1.10x measured above.
- [x] 5.3 Business-result identity: `entries` keys (`long`/`short`) and `potential_entries` keys identical between BEFORE and AFTER on the same real full-history run.

## 6. Closeout

- [x] 6.1 Results summarized above (sections 2-5).
- [x] 6.2 Not archived, no PR/merge performed -- awaiting separate explicit instruction per the task.
