Groups are ordered so that each group ends in a green, verifiable
state. The no-regression gate (group 0) runs again at the end of
every group.

## 0. Baseline

- [ ] 0.1 Record the pre-change baseline on the current `main`:
      - parity corpus outputs;
      - memo compute counts per node family
        (`tests/parity/test_all_families_memo.py` style);
      - `plan_hash` for every corpus spec.
- [ ] 0.2 Add a regression test that compares these against the
      baseline for specs without `composite_setup` (bit-exact outputs,
      identical counts, identical `plan_hash`).

## 1. Static contract and validation

- [ ] 1.1 Add `composite_setup` to `SETUP_SUPPORTED`
      (`raw_spec_identity.py`).
- [ ] 1.2 Implement market-data-free validation of the composite shape
      in `static_semantics.py` (design D1, D2, D3, D12):
      - children, paths and references;
      - no unreferenced children, no nested composite, no nested
        `instance_id`/`context_consumption`, no `/` in ids;
      - predicate classes, ops, operand shapes, kinds, periods and
        `context_ref` existence;
      - `short`/`side_relative` exclusivity;
      - temporal `of` is non-temporal.
- [ ] 1.3 Unit tests: one rejection test per validation rule, plus
      acceptance of the owner's example spec (two paths, HTF, ADX
      1h/5m, RSI, `at_least`).

## 2. Composite skeleton with semantic setup children

- [ ] 2.1 `feature_plan.py`: recurse into composite setup children and
      plan them by the existing per-component code under the key
      `"{instance_id}/{child_id}"`.
- [ ] 2.2 `setups.py`:
      - composite branch in `_setup`;
      - semantic child adapter, local mask only, no gate;
      - vectorized path evaluation (`require` AND, `at_least` count ≥ k,
        OR across paths);
      - trace per design D11.
- [ ] 2.3 `resolve_setup_local`: identities per design D10.
      Semantic children reuse the existing local identity unchanged.
- [ ] 2.4 `live_calculation_requirements.py`: recurse into semantic
      children; fail closed on unknown child kinds.
- [ ] 2.5 Tests:
      - a single-child composite equals the plain setup (mask and
        feature compute count);
      - OR across paths and `at_least` bounds;
      - `winning_path` order;
      - memoized vs non-memoized bit-exact, with zero
        `unforeseen_consumptions`.
- [ ] 2.6 Run the group 0 regression gate.

## 3. Predicates over canonical features

- [ ] 3.1 New `predicates.py`: parsing of feature, price and constant
      operands. Feature operands map to `PlannedFeature` through the
      existing label functions.
- [ ] 3.2 `feature_plan.py`: plan predicate feature operands via the
      existing `add()`.
- [ ] 3.3 Label collision check (design D7): the requested identity
      must equal the identity under the label, otherwise
      `InvalidRequestError`.
- [ ] 3.4 Memoized `predicate.column` node: one float64 read-only
      array per feature identity, NaN for missing (design D8).
- [ ] 3.5 `compare` and `range`, vectorized. Non-finite values give
      False (D5). Side handling covers side-free, `short` override and
      `side_relative` (D3).
- [ ] 3.6 Resolve twins for column, compare and range. A side-free
      predicate has no side in its identity.
- [ ] 3.7 Live history: an explicit zero-additional entry for
      non-temporal predicates.
- [ ] 3.8 Tests:
      - each class on hand-built frames against a naive per-bar
        reference implemented in the test;
      - HTF operand values equal the aligned plan column;
      - shared feature with an existing blocker or exit is planned
        once;
      - EMA source collision fails closed;
      - three predicates on one column cause one conversion.
- [ ] 3.9 Run the group 0 regression gate.

## 4. Context state and temporal predicates

- [ ] 4.1 `evaluation.py`: pass the `ContextBundle` into
      `evaluate_setups`, and `resolve_context_bundle` identities into
      `resolve_setups` (design D9).
- [ ] 4.2 `state` predicate: read the bundle state for `context_ref`
      and map it per side through `resolve_htf_regime`. No EMA
      computation.
- [ ] 4.3 `temporal` `held_for` and `within` in O(n), independent of N,
      through a cumulative sum and a shifted difference (design D4).
      `held_for` is False while fewer than N bars exist; `within` uses
      a shortened window.
- [ ] 4.4 Resolve twins for `state` and `temporal`.
- [ ] 4.5 Live history: `bars − 1` additional base bars per temporal
      predicate.
- [ ] 4.6 Tests:
      - the spec scenarios for `held_for`, `within` and the start of
        history;
      - `state` long/short mapping;
      - a mixed 5m/15m/1h/4h composite on real market fixture data
        against a naive per-bar reference;
      - memoized vs non-memoized bit-exact.
- [ ] 4.7 Run the group 0 regression gate.

## 5. End-to-end and cost verification

- [ ] 5.1 Owner example end-to-end. Run the two-path spec (HTF held,
      ADX 1h/5m, RSI, `at_least`) through `/range-batch`. Check the
      final masks and `winning_path` against the naive reference.
- [ ] 5.2 Wall-clock A/B on the `batch-computation-reuse` benchmark
      workload (BTCUSDT.P 5m, real sweep requests) for specs without
      `composite_setup`. There must be no regression beyond noise.
      Record the numbers in `benchmark-report.md`.
- [ ] 5.3 Composite overhead measurement. Compare a single-child
      composite with the plain setup: feature compute counts must be
      equal. Record the time difference.
- [ ] 5.4 Lint, format, typecheck and the full test suite.

## 6. Spec sync

- [ ] 6.1 After review, sync the delta specs into `openspec/specs/` and
      archive the change.
