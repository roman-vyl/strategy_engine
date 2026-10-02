## 1. Atom

- [x] 1.1 `mfe_r` in the single-trade managed evaluation: initial risk
      frozen at entry from `initial_stop_price`, unmet with reason
      `initial_risk_unavailable` when it is absent or not positive.
      Verify: `tests/test_ema_pullback_mfe_r.py` covers long and short,
      the unit of the threshold, the missing stop and a non-positive
      threshold.
- [x] 1.2 Live start-after-entry evaluation uses the receipt initial
      stop. Verify: a test reaches `proven` from the receipt stop.
- [x] 1.3 `evaluate_managed_replay` accepts an optional
      `initial_stop_price`; the HTTP wire is unchanged.

## 2. Projection and composite

- [x] 2.1 `TradeMetric` gains `mfe_r`; the projection emits a constant
      R threshold for atomic rules and composite trade children.
      Verify: a test reads the rule's `trade_metric` and the constant
      series.
- [x] 2.2 `mfe_r` is accepted as a composite trade child; it needs no
      planned feature and no history window. Verify: composite
      validation test and the plan test.

## 3. Gate

- [x] 3.1 `make verify` equivalent: ruff, mypy and the full suite
      (without `tests/parity`) are green.
- [x] 3.2 `openspec validate mfe-r-phase-threshold-v1 --strict` passes.
