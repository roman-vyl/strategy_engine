## 1. Component

- [ ] 1.1 `r_stop` in `managed.py`: validate `mode` and its parameter,
      compute the candidate from frozen `initial_risk` and the current
      `mfe_price`, discard it when not tighter than the initial stop,
      no candidate without initial risk. Verify: long/short tests for
      lock and trail, monotonic trail on a retrace, no initial stop.
- [ ] 1.2 Zero lookback and no planned feature for `r_stop`
      (`feature_plan`, `live_calculation_requirements`). Verify: plan
      test.
- [ ] 1.3 Equivalence: `break_even_stop{none, 0}` and
      `r_stop{lock, 0}` produce identical active-stop timelines.

## 2. Projection

- [ ] 2.1 `ManagedStopActionRule.stop_basis`, serialized only when set;
      `r_stop` emits a constant distance series. Verify: projection
      shape test; existing projection golden unchanged.
- [ ] 2.2 Parity: a projection consumer reproduces `managed.py`'s
      active stop bar for bar for lock and trail.

## 3. Gate

- [ ] 3.1 ruff, mypy and the full suite (without `tests/parity`) green.
- [ ] 3.2 `openspec validate initial-r-stop-management-v1 --strict`.
