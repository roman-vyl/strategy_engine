## 1. Sparse decision-event contract

- [x] 1.1 Define `StrategyDecisionEvent`/`StrategyEvaluationExecution`
      (plus `DecisionEntry`/`DecisionSignalExit`/`DecisionStopReady` and
      `StrategyDiagnosticEvaluation`) in `strategies/contracts.py`.
      `StrategyRangeResult`/legacy `evaluate()` remain on
      `EmaPullbackRangeEvaluator` as a private implementation detail (no
      route reaches them any more — see 1.4/3.1/3.2, route cutover is
      done).
- [x] 1.2 Implemented as `build_decision_events`
      (`strategies/decision_events.py`, pure function, unit-tested) and
      `EmaPullbackRangeEvaluator.evaluate_execution` (new method,
      `strategies/ema_pullback/evaluator.py`), which builds it from the
      already-native `entries`/`exit_policy` tuples
      (`EmaPullbackEvaluation`) — no string-boxing was ever involved in
      these specific fields.
- [x] 1.3 `build_decision_events` raises `EvaluationInvariantError` (500,
      fail loudly) if `entries_long[i]` and `entries_short[i]` are both
      true — unit-tested (`test_simultaneous_long_and_short_entry_fails_loudly`).
- [x] 1.4 Route cutover done: `/v1/strategy-evaluations/range` and
      `/range-batch` now serialize `StrategyEvaluationExecution` via
      `serialize_strategy_evaluation_execution` — no `time_ms` field on
      the wire at all. Verified by `test_range_response_exact_key_set`/
      `test_batch_variant_outcome_result_exact_key_set` (exact key-set
      assertions, no `time_ms`/`features`/etc present).
- [x] 1.5 Structurally guaranteed by construction: `build_decision_events`
      only ever emits `bar_index` values from `range(bar_count)` — there
      is no code path that could emit one outside `[0, bar_count)`.
      Verified by `test_execution_contract_decision_events_bar_index_within_bar_count`.

## 2. Single-instance parity proof (must complete before task 4)

- [ ] 2.1 Run both the old dense contract and the new sparse contract
      against the same `full_available` BTCUSDT.P/5m request (same
      strategy, same window) and diff per "Parity means" in design.md:
      `TradeRecord` sequence identical, accounting totals exact, exit
      reasons exact trade-for-trade, provenance semantically equal
      (`market_data_hash`/`bar_count`/`config_hash`/`instance_id`) — not
      a byte-identical full artifact diff (`time_ms` removal makes that
      comparison meaningless by design).
- [ ] 2.2 Measure and record CPU time, peak RSS, and response body size
      for both, side by side.
- [ ] 2.3 Do not proceed to task 4 until 2.1 shows zero diffs by the
      "Parity means" definition.

## 3. Split diagnostics out of the mandatory path

- [x] 3.1 Done. `/v1/strategy-evaluations/range` and `/range-batch` now
      return only `StrategyEvaluationExecution` (no `features`/
      `contexts`/`component_evidence`/`potential_entries`/`entries`/
      `exit_policy`/`validity`/`state_artifact` fields exist on that
      type at all). `EvaluateStrategyRange.execute` (application service)
      returns it directly; the legacy dense `evaluate()`/
      `StrategyRangeResult` path is no longer reachable from any route.
- [x] 3.2 Done. New route `POST /v1/strategy-evaluations/range/
      diagnostics` (`evaluate_strategy_range_diagnostics`) calls
      `EvaluateStrategyRange.execute_diagnostics` →
      `EmaPullbackRangeEvaluator.evaluate_diagnostics` → native
      computation, boxed only at this route's own serialization
      (`serialize_strategy_diagnostic_evaluation`). This is the only
      route that returns dense per-bar diagnostic data.
- [x] 3.3 **RESOLVED — Decision: Variant 3, internal-only native fast
      path.** Not a partial/compatibility outcome: strategy evaluation
      never boxes to string, and the public indicator contract is
      untouched.
      - `NativeFeatureFrame` (`indicators/contracts.py`): same shape as
        `FeatureFrame`, `series: dict[str, tuple[float | None, ...]]` --
        never string-boxed, not exposed on any HTTP contract.
      - `RangeIndicatorEvaluator.evaluate_native` is now the **single
        source of indicator computation** -- `evaluate` (the public,
        `ema-indicator-vertical-slice-v1`-governed contract) is a thin
        boxing wrapper over it (`series = {... serialize_value(v) for v
        in native.series[...]}`), not a second formula implementation.
      - `EvaluateIndicatorRange` gained `execute_native` (same
        market-acquisition/hash-validation as `execute`, calls
        `evaluator.evaluate_native` instead) via a shared `_prepare`
        helper -- no duplicated orchestration either.
      - `FeatureFrameLike` (`Protocol`, read-only properties) lets every
        `ema_pullback/{evaluation,contexts,direction_blockers,setups,
        triggers,exits,potential_entries}.py` function accept either
        `FeatureFrame` or `NativeFeatureFrame` -- one formula
        implementation, not a native/legacy fork. `FeatureFrame` itself
        was NOT touched/blurred with a union value type.
      - `EmaPullbackRangeEvaluator._evaluate_frame_native` (used by
        `evaluate_execution`/`evaluate_diagnostics`) calls
        `execute_native`; `_evaluate_frame` (legacy `evaluate()` only)
        still calls the boxed `execute`, unchanged.
      - `evaluate_diagnostics` boxes `frame.series` via `serialize_value`
        only at its own output-boundary dict construction -- the one
        place per acceptance criterion 2 diagnostics are allowed to box.
      - All 8 acceptance criteria proven, see `tests/test_native_fast_path.py`:
        (1) `test_evaluate_execution_never_calls_serialize_value` --
        monkeypatches `serialize_value` in both call-site modules,
        asserts zero calls during `evaluate_execution()`; (2)/(3) same
        test -- zero boxing means zero reverse-parsing too, there is
        nothing to reparse; (4)/(5) all pre-existing indicator
        vertical-slice tests pass unchanged (no expected-value
        rewrites); (6) all pre-existing strategy tests pass unchanged;
        (7) the monkeypatch spy IS the required regression guard --
        `test_evaluate_diagnostics_boxes_only_at_the_output_boundary`
        and `test_legacy_evaluate_still_boxes_features_when_requested`
        are positive controls proving the spy actually fires when it
        should, so criterion (1)'s zero-calls assertion is meaningful,
        not vacuous; (8)
        `test_native_and_boxed_computation_agree_numerically` --
        native output vs boxed-then-reparsed output compared bar-for-
        bar, series-for-series, for the same input; structurally
        enforced by `evaluate` calling `evaluate_native` rather than
        recomputing.
      - Full suite: 389 passed (372 baseline + 17 new across this and
        prior sub-tasks), ruff clean, mypy clean (89 files).

## 4. Batch adoption (only after task 2 passes)

- [ ] 4.1 `EvaluateStrategyRangeBatch`/`evaluate_strategy_range_batch`
      route adopt the same compact per-variant
      `StrategyEvaluationExecution` result — no separate batch-only
      strategy semantics. **This alone does not bound batch memory in
      N** — `outcomes`/`{"variants":[...]}"` still accumulate all N
      results before responding, just each is now small.
- [ ] 4.2 Separate, binding: change the aggregation pattern so N
      candidates are evaluated, delivered, and released one at a time —
      never all N held resident simultaneously — while retaining
      shared-L0 acquisition. Coordinate the exact mechanism with the
      companion `research_service` change (transport/call-pattern is an
      implementation decision, not fixed by this proposal).
- [ ] 4.3 Only after 4.2: re-run the N=1/2/4/11 memory/CPU harness from
      the earlier diagnostic pass this session; confirm approximately
      constant memory in N.

## 5. Spec

- [ ] 5.1 `openspec archive compact-strategy-evaluation-boundary-v1`
      after implementation lands, parity is proven, and the acceptance
      criteria in `design.md` are met.
