## 1. Sparse decision-event contract

- [ ] 1.1 Define `StrategyDecisionEvent` and `StrategyEvaluationExecution`
      types (`strategies/contracts.py`), replacing the execution-facing
      fields of `StrategyRangeResult` (`entries`, `exit_policy`) — leave
      `StrategyRangeResult` itself as the internal-only shape that still
      carries diagnostics for now (split fully in task 3).
- [ ] 1.2 Implement sparse event emission in
      `EmaPullbackRangeEvaluator.evaluate`: walk the currently-dense
      `entries`/`exit_policy` computation internally (native/dense is
      fine *inside* the evaluator — the wire boundary is what changes),
      emit one `StrategyDecisionEvent` per bar carrying at least one of
      entry/signal_exit/stop_ready.
- [ ] 1.3 Add the mutual-exclusivity assertion at the point where a
      per-bar entry decision is finalized into an event — fail loudly on
      violation, do not silently pick a side.
- [ ] 1.4 Drop `time_ms` from the wire response entirely.
- [ ] 1.5 Enforce the `bar_index` invariant (design.md) — every emitted
      `bar_index` is within `[0, bar_count)` for the range the response's
      own `market_data_hash`/`bar_count` describe.

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

- [ ] 3.1 Move `features`, `contexts`, `component_evidence`,
      `potential_entries` off the mandatory range-evaluation response
      type entirely.
- [ ] 3.2 Add the diagnostic-evaluation entrypoint (application service +
      route) per the ownership/provenance contract fixed in design.md:
      Engine computes, request identifies strategy+market+expected hash
      the same way an execution-evaluation request does, response
      provenance (`config_hash`/`market_data_hash`/`bar_count`) matches
      what the corresponding execution evaluation would produce. This is
      the only place dense per-bar diagnostic data is computed/returned.
- [ ] 3.3 Confirm `RangeIndicatorEvaluator.evaluate`'s unconditional
      string-boxing of `FeatureFrame.series` no longer executes on the
      mandatory execution path — only reachable via the diagnostic
      entrypoint from 3.2.

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
