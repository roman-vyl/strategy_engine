## 1. Sparse decision-event contract

- [x] 1.1 Define `StrategyDecisionEvent`/`StrategyEvaluationExecution`
      (plus `DecisionEntry`/`DecisionSignalExit`/`DecisionStopReady` and
      `StrategyDiagnosticEvaluation`) in `strategies/contracts.py`.
      `StrategyRangeResult` left as-is (internal, still used by the
      legacy `evaluate()` method) — the new types are additive, not a
      replacement of its fields yet; actual route cutover is separate
      remaining work (see status note below task 3.3).
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
- [ ] 1.4 NOT done — the legacy `evaluate()`/`StrategyRangeResult` HTTP
      route (`/range`, `/range-batch`) still serves `time_ms` today. The
      new `StrategyEvaluationExecution`/`evaluate_execution()` has no
      `time_ms` field at all (verified by
      `test_execution_contract_has_no_time_ms_or_diagnostic_fields`), but
      nothing serves it over HTTP yet — route cutover is remaining work.
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

- [ ] 3.1 PARTIAL — `StrategyEvaluationExecution` (mandatory contract
      type) never has `features`/`contexts`/`component_evidence`/
      `potential_entries` fields at all (they don't exist on that
      dataclass); `StrategyDiagnosticEvaluation` (new, separate type)
      carries them, built by the new `evaluate_diagnostics()` method.
      NOT done: no HTTP route serves `evaluate_execution()`/
      `evaluate_diagnostics()` yet — `/range`/`/range-batch` still call
      the legacy `evaluate()`, which still returns everything combined.
      Route cutover is remaining work, coordinated with the
      `research_service` companion change being ready to consume it.
- [ ] 3.2 PARTIAL — `evaluate_diagnostics()` exists as an application-
      layer method with the right provenance shape (its
      `config_hash`/`market_data_hash`/`bar_count` are proven equal to
      `evaluate_execution()`'s for the same request —
      `test_execution_and_diagnostic_provenance_agree_for_the_same_request`).
      NOT done: no HTTP route exposes it yet.
- [ ] 3.3 **BLOCKED — genuine scope conflict found during implementation,
      not resolved, needs a coordinator decision.** Attempted to change
      `FeatureFrame.series` from `dict[str, tuple[str|None,...]]` to
      native `float|None` (eliminating `RangeIndicatorEvaluator`'s
      `serialize_value` call on the always-executed path). This broke 4
      tests asserting `FeatureFrame.series` values as normalized decimal
      strings, tracing back to `openspec/specs/ema-indicator-vertical-
      slice-v1/spec.md`'s own requirement: "SHALL serialize values as
      normalized decimal text or `null`." `EmaIndicatorEvaluator` (the
      type that spec governs) is a thin wrapper directly around the same
      `RangeIndicatorEvaluator` strategy evaluation uses — they are not
      separate implementations. So `RangeIndicatorEvaluator`/
      `FeatureFrame` is shared, already-spec-governed infrastructure this
      proposal did not declare as an affected capability, and the
      original `4.1`-style claim ("no compatibility shim, get the clean
      target architecture") cannot be honored here without also amending
      `ema-indicator-vertical-slice-v1` (and likely its ATR/RSI/ADX-DMI/
      ATR-distance siblings, which share the same evaluator) — out of
      scope for this proposal as written. Reverted the attempt; all 372
      pre-existing tests pass again. Options for the coordinator: (a)
      accept partial 3.3 — the *mandatory wire response* no longer
      carries dense diagnostics (real, already achieved via 3.1/3.2's
      type split) but `RangeIndicatorEvaluator`'s internal string-boxing
      cost remains paid on every evaluation regardless of path; (b)
      author a companion OpenSpec change against the indicator-vertical-
      slice specs to relax/relocate their string-serialization
      requirement, expanding this migration's scope; (c) a strategy-
      internal-only fast path that duplicates range evaluation without
      going through the shared, spec-governed evaluator (more code, but
      leaves the public indicator contract untouched).

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
