## 1. Implement

- [ ] 1.1 Vectorize `untouched_prior` in `_untouched_anchor` per design.md Decision 1.
- [ ] 1.2 Vectorize `touch_active` in `_untouched_anchor` per design.md Decision 2.
- [ ] 1.3 Vectorize `recent_max` in `_anchor_stack_width` per design.md Decision 3 (finite-window gate required).
- [ ] 1.4 Add `_combine_setup_masks` and use it for `setups_ok` in `evaluate_setups` per design.md Decision 4.
- [ ] 1.5 Add `import numpy as np` / `import pandas as pd` to `setups.py` if not already present.

## 2. Unit parity tests (per fragment)

- [ ] 2.1 `untouched_prior`: edge cases (all-touch, no-touch, alternating), lookback=1, lookback>=len, first/last bar, randomized cases.
- [ ] 2.2 `touch_active`: edge cases, active_bars=1, active_bars>=len, first/last bar, randomized cases.
- [ ] 2.3 `recent_max`: edge cases, lookback=1, insufficient window (index+1<lookback), all-finite window, single-NaN-in-window, all-NaN window, first/last bar, randomized mixed finite/NaN cases.
- [ ] 2.4 `_combine_setup_masks`: empty masks (all True), single mask, multiple all-true, multiple all-false, mixed.

## 3. Broader regression parity

- [ ] 3.1 Full `evaluate_setups` before/after parity on representative strategy fixtures: `setup masks`, `local_setup_allowed`, `final_setup_allowed`, `setups_ok`, `pre_trigger`, and trace fields `untouched_prior`, `touch_active`, `recent_max_width_atr`, `current_width_ok`, `recent_width_ok`, `blocked_reason`.
- [ ] 3.2 Run existing `tests/test_ema_pullback_setups.py` and `tests/test_live_calculation_ema_pullback_requirements.py` unchanged (no modification needed unless a fixture assumption breaks).
- [ ] 3.3 Representative full-history business-result parity (before/after identical) as final regression sanity check.

## 4. Repository quality gates

- [ ] 4.1 `pytest` (full suite).
- [ ] 4.2 `ruff`.
- [ ] 4.3 `mypy`.
- [ ] 4.4 `openspec validate ema-pullback-setup-vectorization --strict`.
- [ ] 4.5 `git diff --check`.

## 5. Real production-path performance acceptance

- [ ] 5.1 Real before/after benchmark on `evaluate_setups` (or the smallest real end-to-end path that exercises it) using representative strategy spec/data, not synthetic-only.
- [ ] 5.2 Report per-fragment and `evaluate_setups`-total timing; do not extrapolate the isolated `recent_max` microbench figure to the whole function or engine.
- [ ] 5.3 Business-result identity check before trusting timing numbers.

## 6. Closeout

- [ ] 6.1 Summarize results in tasks.md.
- [ ] 6.2 Do not archive/PR/merge — await separate explicit instruction.
