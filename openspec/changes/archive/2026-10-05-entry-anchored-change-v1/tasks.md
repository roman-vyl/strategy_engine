## 0. Baseline

- [x] 0.1 Confirm the invariants kept for specs without `change_since_entry`: `plan_hash` and plan labels, memoized node
      identities and compute counts, evaluation outputs, serialized managed projections (atomic and composite). Verify: the
      existing suites that pin them (declared invariants, managed invariants, plan labels, projection serialization) pass
      unchanged after every group.

## 1. Static contract and parsing

- [x] 1.1 Add `change_since_entry` to `PHASE_ATOM_CHILDREN` (`composite_spec.py`). Parse its params market-data-free:
      `operand` through `predicates._operand` (feature only), `op` in `>=`, `>`, `<=`, `<`, `value` finite; reject unknown
      fields, `lookback`, `short`, a price or constant operand, `==`, `!=`. Verify: static validation tests for each rejection
      and for acceptance as a child in `require` and in `at_least`.
- [x] 1.2 Reject `change_since_entry` as the `condition` of a phase rule and in every other list. Verify: tests.

## 2. Single-trade evaluation

- [x] 2.1 `_phase_met` branch: operand column through `SeriesCache`, anchor at `state.entry_index`, value at `index`, False on
      non-finite. Verify: tests on a base and a higher-timeframe operand, entry bar (`>= 0` true), non-finite anchor,
      non-finite current value, all four operators, both sides, offsets 0 and 1.
- [x] 2.2 Composition through `composite_met`: in `require`, in trade-only and mixed `at_least`, attribution of the winning
      path and child values. Verify: tests.

## 3. Projection

- [x] 3.1 Contracts: `ManagedTransitionEntryChange`, `ManagedTransitionPath.entry_changes`, `ManagedTransitionTerm.entry_change`
      (exactly one variant per term). Verify: contract tests.
- [x] 3.2 `_composite_paths`: one series per child in `distances`, entry changes for `require`, terms for `at_least`.
      Verify: projection shape tests.
- [x] 3.3 Serialization omits `entry_changes` when empty and `entry_change` when absent. Verify: byte-identical serialized
      projections for atomic specs and for composite specs without the atom.
- [x] 3.4 Reference consumer in tests: evaluate entry changes as specified. Verify: parity of (bar, `rule_id`, `path_id`)
      with `evaluate_managed_replay` on a corpus of entries and both sides, for `require` and for mixed `at_least`.

## 4. Planning

- [x] 4.1 Feature plan: the operand joins the predicate features of composite phase condition children. Verify: plan test with
      the atom; unchanged `plan_hash` for specs without it.
- [x] 4.2 Live history: explicit zero entry for the child. Verify: planner test.

## 5. Gate

- [x] 5.1 ruff, mypy, the full suite (without `tests/parity`) are green.
- [x] 5.2 `openspec validate entry-anchored-change-v1 --strict` passes.
