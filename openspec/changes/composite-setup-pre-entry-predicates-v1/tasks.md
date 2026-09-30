Groups are ordered so that each group ends in a green, verifiable
state. The no-regression gate (group 0) runs again at the end of
every group.

## 0. Baseline

- [x] 0.1 Record the pre-change baseline on the current `main` for the
      existing parity corpus (specs without `composite_setup`). Record
      only the quantities this change promises to keep invariant:
      - the public strategy evaluation result as already compared by
        the parity harness (`tests/parity/compare.py`): decision masks,
        entries and exit results;
      - `plan_hash` and the ordered plan feature labels;
      - the multiset of memoized node identities and the compute
        counts per node family (`tests/parity/test_all_families_memo.py`
        style);
      - `IndicatorRegistry` responses (`list_definitions`, `get_schema`)
        and `resolve_feature` identities for every existing kind.
- [x] 0.2 Add a regression test that asserts exactly these invariants
      against the baseline for specs without `composite_setup`.
      - The artifact SHALL NOT be a snapshot of whole internal
        serializations. Trace key order, reprs, debug-only fields,
        timings and unrelated wire fields are out.
      - A change unrelated to this change's invariants must not break
        it.
      - Each asserted quantity names the invariant it protects: design
        D6, D13, and the `batch-computation-reuse` no-regression
        requirement.

## 1. Static contract and validation

- [x] 1.1 Add `composite_setup` to `SETUP_SUPPORTED`
      (`raw_spec_identity.py`).
- [ ] 1.2 (structure done in `composite_spec.py`; predicate-child validation lands
      with group 4) Implement market-data-free validation of the composite shape
      in `static_semantics.py` (design D1, D2, D3, D12):
      - children, paths and references;
      - no unreferenced children, no nested composite, no nested
        `instance_id`/`context_consumption`, no `/` in ids;
      - predicate classes, ops, operand shapes and `context_ref`
        existence; feature operands are validated through the canonical
        feature-kind contract (design D13), not by local rules;
      - `short` override only on `compare`/`range`; `side_relative` or
        any automatic inversion flag is rejected;
      - temporal `of` is non-temporal.
- [x] 1.3 Unit tests: one rejection test per validation rule, plus
      acceptance of the owner's example spec (two paths, HTF, ADX
      1h/5m, RSI, `at_least`).

## 2. Composite skeleton with semantic setup children

- [x] 2.1 `feature_plan.py`: recurse into composite setup children and
      plan them by the existing per-component code under the key
      `"{instance_id}/{child_id}"`.
- [x] 2.2 `setups.py`:
      - composite branch in `_setup`;
      - semantic child adapter, local mask only, no gate;
      - vectorized path evaluation (`require` AND, `at_least` count ≥ k,
        OR across paths);
      - trace per design D11.
- [x] 2.3 `resolve_setup_local`: identities per design D10.
      Semantic children reuse the existing local identity unchanged.
- [x] 2.4 `live_calculation_requirements.py`: recurse into semantic
      children; fail closed on unknown child kinds.
- [x] 2.5 Tests:
      - a single-child composite equals the plain setup (mask and
        feature compute count);
      - OR across paths and `at_least` bounds;
      - `winning_path` order;
      - memoized vs non-memoized bit-exact, with zero
        `unforeseen_consumptions`.
- [x] 2.6 Run the group 0 regression gate.

## 3. Canonical feature-kind contract (indicator layer, design D13)

- [ ] 3.1 Add `indicators/feature_kinds.py` with one `FeatureKindContract`
      per existing kind (`ema`, `atr`, `atr_distance`, `rsi`, `adx`,
      `di_plus`, `di_minus`). Each entry holds the schema (moved from
      `service/registries.py`), the default source, the `requestable`
      flag, the existing validator, the label and the identity params.
      Also add `feature_kind()`, `feature_kinds()` and
      `plan_feature_request()`.
- [ ] 3.2 Make `IndicatorRegistry` delegate to `feature_kinds()`.
      Responses and validation errors must stay unchanged.
- [ ] 3.3 In `feature_plan.py`, derive `_ALLOWED_KINDS` from the
      contract and route the label functions through
      `FeatureKindContract.label`. Labels must stay unchanged.
- [ ] 3.4 In `resolve_feature`, build identity params as
      `{timeframe, source, **identity_params}`. Identities of existing
      kinds must stay unchanged, and `atr_distance` keeps its explicit
      dependency identity.
- [ ] 3.5 Tests:
      - registry responses, labels and identities of every existing
        kind are unchanged (group 0 artifacts);
      - an unknown kind fails closed;
      - a test-only contract entry for a fake kind with an extra
        parameter gets distinct identities per parameter value.
- [ ] 3.6 Run the group 0 regression gate.

## 4. Predicates over canonical features

- [ ] 4.1 New `predicates.py`: parse feature, price and constant
      operands.
      - Feature operands are opaque requests resolved only via
        `plan_feature_request` (design D13).
      - The module has no kind names, no source rules and no parameter
        rules.
      - Add an architecture test: `predicates.py` contains no
        indicator-kind string literals and imports nothing from
        `indicators/implementations`.
- [ ] 4.2 `feature_plan.py`: plan predicate feature operands via the
      existing `add()`.
- [ ] 4.3 Label collision check (design D7): the requested identity
      must equal the identity under the label, otherwise
      `InvalidRequestError`.
- [ ] 4.4 Memoized `predicate.column` node: one float64 read-only
      array per feature identity, NaN for missing (design D8).
- [ ] 4.5 `compare` and `range`, vectorized. Non-finite values give
      False (D5). Predicates are side-free by default; the short side
      differs only through an explicit `short` override (D3).
- [ ] 4.6 Resolve twins for column, compare and range. A side-free
      predicate has no side in its identity.
- [ ] 4.7 Live history: an explicit zero-additional entry for
      non-temporal predicates.
- [ ] 4.8 Tests:
      - each class on hand-built frames against a naive per-bar
        reference implemented in the test;
      - HTF operand values equal the aligned plan column;
      - shared feature with an existing blocker or exit is planned
        once;
      - EMA source collision fails closed;
      - three predicates on one column cause one conversion.
- [ ] 4.9 Run the group 0 regression gate.

## 5. Context state and temporal predicates

- [ ] 5.1 `evaluation.py`: pass the `ContextBundle` into
      `evaluate_setups`, and `resolve_context_bundle` identities into
      `resolve_setups` (design D9).
- [ ] 5.2 `state` predicate: read the bundle state for `context_ref`
      and map it per side through `resolve_htf_regime`. No EMA
      computation.
- [ ] 5.3 `temporal` `held_for` and `within` in O(n), independent of N,
      through a cumulative sum and a shifted difference (design D4).
      `held_for` is False while fewer than N bars exist; `within` uses
      a shortened window.
- [ ] 5.4 Resolve twins for `state` and `temporal`.
- [ ] 5.5 Live history: `bars − 1` additional base bars per temporal
      predicate.
- [ ] 5.6 Tests:
      - the spec scenarios for `held_for`, `within` and the start of
        history;
      - `state` long/short mapping;
      - a mixed 5m/15m/1h/4h composite on real market fixture data
        against a naive per-bar reference;
      - memoized vs non-memoized bit-exact.
- [ ] 5.7 Run the group 0 regression gate.

## 6. End-to-end and cost verification

- [ ] 6.1 Owner example end-to-end. Run the two-path spec (HTF held,
      ADX 1h/5m, RSI, `at_least`) through `/range-batch`. Check the
      final masks and `winning_path` against the naive reference.
- [ ] 6.2 Wall-clock A/B on the `batch-computation-reuse` benchmark
      workload (BTCUSDT.P 5m, real sweep requests) for specs without
      `composite_setup`. There must be no regression beyond noise.
      Record the numbers in `benchmark-report.md`.
- [ ] 6.3 Composite overhead measurement. Compare a single-child
      composite with the plain setup: feature compute counts must be
      equal. Record the time difference.
- [ ] 6.4 Lint, format, typecheck and the full test suite.

## 7. Spec sync

- [ ] 7.1 After review, sync the delta specs into `openspec/specs/` and
      archive the change.
