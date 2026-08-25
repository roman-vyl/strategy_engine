## 1. Implement the vectorized replacements

- [ ] 1.1 Add `import numpy as np` (and `import pandas as pd` if not already present) to `src/strategy_engine/strategies/ema_pullback/direction_blockers.py`.
- [ ] 1.2 Replace `_rsi_blocker`'s per-bar loop with the `np.isfinite` gate + `pandas.Series.rolling(lookback, min_periods=1).max()` implementation (design.md Decision 1). Signature and return type (`tuple[tuple[bool,...], dict[str, tuple[object,...]]]`) unchanged; `trace` dict keys (`"rsi"`, `"extreme_seen"`) unchanged.
- [ ] 1.3 Replace `_trend_strength_blocker`'s nested backward-scan loop with the running-last-qualifying-index implementation (design.md Decision 2), preserving the exact elif-chain priority order and all four output arrays (`allowed`, `blocked_reason`, `adx_peak_idx`, `bars_since_adx_peak`) and their dtypes (bool / str / int).
- [ ] 1.4 Replace `evaluate_direction_and_blockers`'s final `all(...) for index in range(...)` combine with `np.logical_and.reduce(..., initial=True)` plus the explicit empty-blockers branch (design.md Decision 3).
- [ ] 1.5 Confirm by reading: no other function in `direction_blockers.py` is touched; call sites (`_blocker()` for 1.2/1.3, `evaluate_direction_and_blockers` for 1.4) are unchanged.

## 2. Unit parity tests (extend the existing direction-blockers test file in place)

- [ ] 2.1 `_rsi_blocker`: normal, warmup NaN, all-pass, all-block, alternating, long/short, threshold equality, `lookback=1`, `lookback` > frame length, all-NaN, `+inf`/`-inf`, first/last bar.
- [ ] 2.2 `_trend_strength_blocker`: normal random/reference case, current `indicator_not_ready`, candidate NaN inside the lookup window (current bar finite), no recent peak, peak too old, `min_peak` exact equality, `min_current` exact boundary, `require_alignment` true/false, `block_flip` true/false, DI margin, long/short, `peak_lookback_bars=1`, first/last bar, `max_since` exact boundary, `+inf`/`-inf`. For every case, assert exact parity on all four outputs -- `allowed`, `blocked_reason`, `adx_peak_idx`, `bars_since_adx_peak` -- not `allowed` alone. Include at least one case specifically constructed so more than one blocking condition holds on the same bar, to prove reason-priority ordering is preserved.
- [ ] 2.3 Final combine: empty, one blocker, multiple blockers, all-true, all-false, mixed masks.

## 3. Broader regression parity

- [ ] 3.1 Full existing `direction_blockers`/related test suite passes unchanged.
- [ ] 3.2 Representative `evaluate_ema_pullback_frame`/`EmaPullbackEvaluation` regression: existing representative-spec tests confirm no change to any field.
- [ ] 3.3 Full-history business-result parity: same real-infra scenario as prior audits (ETHUSDT.P 5m, full history, canonical spec) -- `EvaluateStrategyRange.execute` result identical before/after on the fields the audit's business-tuple check already covers (entries tail, exit_policy signal/ready tail, warnings), extended to also cover `direction_blockers`/`blockers_ok`-derived fields if reachable from `StrategyRangeResult`.

## 4. Repository quality gates

- [ ] 4.1 `pytest`
- [ ] 4.2 `ruff check src tests scripts`
- [ ] 4.3 `mypy src`
- [ ] 4.4 `openspec validate direction-blockers-vectorization --strict`
- [ ] 4.5 `git diff --check`

## 5. Real full-history performance acceptance

- [ ] 5.1 Reproduce the same real local infrastructure and full-history scenario used in the prior audits: production `build_services(settings)`, real local MDS HTTP, real DB, ETHUSDT.P 5m, full available history (~572,900+ bars, exact count recorded at run time), `EvaluateStrategyRange.execute` -> `EmaPullbackRangeEvaluator`.
- [ ] 5.2 1 warm-up + 3 measured runs before this change (pre-change commit, temporary worktree) and after (current branch), recording: `_rsi_blocker`, `_trend_strength_blocker`, final-combine, `direction_blockers` total, and full backtest total -- for each run plus median.
- [ ] 5.3 Confirm all before-runs and all after-runs produce an identical business result, and before matches after exactly.
- [ ] 5.4 Record speedup (x) and absolute seconds saved for `direction_blockers` total and full backtest total. Synthetic audit-benchmark numbers are not treated as the acceptance proof -- this real full-history measurement is.

## 6. Closeout

- [ ] 6.1 Confirm the changed-file set matches the proposed scope exactly: `src/strategy_engine/strategies/ema_pullback/direction_blockers.py` (production) and the existing direction-blockers test file (extended in place) -- no other file touched.
- [ ] 6.2 Record final before/after numbers (Group 5) and parity confirmation (Groups 2-3) in this file or the closing report. Do not archive/PR/merge without a separate explicit instruction.
