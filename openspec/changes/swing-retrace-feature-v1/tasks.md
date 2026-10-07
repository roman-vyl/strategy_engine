## 0. Baseline

- [ ] 0.1 Record the invariants for specs without `swing_retrace` and `if_missing`: plan labels, `plan_hash`, memoized node
      identities and compute counts, `IndicatorRegistry` responses. Verify: the existing suites that pin them pass unchanged.

## 1. Kind contract

- [ ] 1.1 Schema, validator, label and identity parameters of `swing_retrace` in `feature_kinds.py` (design D5). Verify: tests for
      every rejection (unknown `direction`/`measure`/`anchor`, non-positive `bars`, `touch_period` or `stack_periods` with
      `window`, missing `touch_period` with `ema_touch`, `stack_periods` shorter than 2, not strictly increasing, or empty) and for
      distinct identities when any parameter differs.

## 2. Math

- [ ] 2.1 `window` anchor with monotonic deques, both measures, both directions (design D2, D4).
- [ ] 2.2 `ema_touch` anchor with a sparse table, canonical EMA math, optional stack (design D2, D4).
- [ ] 2.3 Reference loop test: vectorized equals a plain per-bar implementation of D2 on a seeded random walk for every parameter
      combination in a small grid; hand-built cases for ties, `H ≤ 0`, `retrace_bars = 0`, no touch within `bars`, stack start
      after the last touch.
- [ ] 2.4 Higher timeframe: values come only from completed bars; the aligned column on base bars inside a bucket equals the
      value of the previous completed bucket. Verify: test on 1h and 4h.

## 3. Predicate option

- [ ] 3.1 Parse `if_missing` on `compare`, `range`, `change`; reject it on `state`, `temporal`, in `short`; include it in the
      predicate identity. Verify: tests.
- [ ] 3.2 Evaluate: True on missing bars when set; default identical to today. Verify: tests, including warm-up bars.

## 4. Planning

- [ ] 4.1 Live history policy for `swing_retrace` (spec delta). Verify: planner tests; a later-starting window equals the full window
      wherever both are defined.

## 5. Gate

- [ ] 5.1 Group 0 regression green after every group.
- [ ] 5.2 ruff, mypy, the full suite (without `tests/parity`) green.
- [ ] 5.3 `openspec validate swing-retrace-feature-v1 --strict` passes.
