## 0. Baseline

- [x] 0.1 Record the invariants this change promises to keep for specs without a `change` predicate: evaluation outputs on the
      parity corpus, `plan_hash` and plan labels, memoized node identities and compute counts per node family,
      `IndicatorRegistry` responses and `resolve_feature` identities. Verify: the existing suites that already pin them (memoized node identities and compute counts, plan labels, the predicate and composite tests) pass unchanged; no new baseline artifact was added.

## 1. Static contract and parsing

- [x] 1.1 Parse `change {operand, lookback, op, value}` in `predicates.py` (market-data-free): feature operand through the canonical
      feature-kind contract, `lookback` positive integer, `op` in `>`, `>=`, `<`, `<=`, `value` finite number; reject unknown
      fields, `==`, `!=`, a second operand, a non-feature operand, a `temporal` wrapper around a temporal predicate unchanged.
      Verify: static validation tests for each rejection and for acceptance as a `composite_setup` child and as a
      `composite_phase_condition` child.
- [x] 1.2 Extend the `short` override to `change` for `op` and `value` only. Verify: tests for accepted and rejected override fields.

## 2. Evaluation

- [x] 2.1 `evaluate_predicate` for `change`: shifted aligned column by `lookback * k` base bars, difference, comparison, False on a
      non-finite or out-of-frame point. Verify: tests on a base-timeframe feature, on a higher-timeframe feature (k > 1), at the start
      of the frame, with non-finite values, and the D2 equivalence test (aligned column shifted by `lookback * k` equals the value of completed
      bar `j - lookback` on every base bar, real evaluator, epoch-aligned and mid-bucket frame starts, a one-row-off mutant fails), for all four operators and both sides with and without override.
- [x] 2.2 Composition: `held_for` and `within` over `change`; `change` inside a composite path with other children.
      Verify: predicate-level tests only. Managed evaluation and the historical projection are not touched by this change.
- [x] 2.3 Determinism: repeated evaluation is identical. Verify: test.

## 3. Planning and identity

- [x] 3.1 Live history policy: `_predicate_history` returns the `lookback` bars of the operand's timeframe for `change`, and adds the
      window under `temporal`. Verify: planner tests for a base feature, a higher-timeframe feature and `held_for` over `change`.
- [x] 3.2 Identity twin `predicate.change` through `resolve_predicate`; a memoized evaluation ends with zero
      `unforeseen_consumptions`. Verify: memo tests; identical outputs memoized and not.

## 4. Gate

- [x] 4.1 The group 0 regression test is green after every group.
- [x] 4.2 ruff, mypy, the full suite (without `tests/parity`) are green. Note: `tests/test_declared_invariants_live_entry.py::test_live_entry_responses_unchanged` fails on `main` without this change as well and is not caused by it; `tests/parity` was not run (excluded from the mandatory gate).
- [x] 4.3 `openspec validate predicate-change-class-v1 --strict` passes.
