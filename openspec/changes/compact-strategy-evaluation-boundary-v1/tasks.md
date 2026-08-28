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

## 2. Single-instance parity proof (must complete before task 4)

- [ ] 2.1 Run both the old dense contract and the new sparse contract
      against the same `full_available` BTCUSDT.P/5m request (same
      strategy, same window) and diff: trade-by-trade fields, accounting
      totals, exit reasons, provenance (`market_data_hash`).
- [ ] 2.2 Measure and record CPU time, peak RSS, and response body size
      for both, side by side.
- [ ] 2.3 Do not proceed to task 4 until 2.1 shows zero diffs.

## 3. Split diagnostics out of the mandatory path

- [ ] 3.1 Move `features`, `contexts`, `component_evidence`,
      `potential_entries` off the mandatory range-evaluation response
      type entirely.
- [ ] 3.2 Add a separate diagnostic-evaluation entrypoint (application
      service + route) that Research's on-demand diagnostics-generation
      flow (companion change) can call for one already-evaluated
      strategy/range/market_data_hash — this is the only place dense
      per-bar diagnostic data is computed/returned.
- [ ] 3.3 Confirm `RangeIndicatorEvaluator.evaluate`'s unconditional
      string-boxing of `FeatureFrame.series` no longer executes on the
      mandatory execution path — only reachable via the diagnostic
      entrypoint from 3.2.

## 4. Batch adoption (only after task 2 passes)

- [ ] 4.1 `EvaluateStrategyRangeBatch`/`evaluate_strategy_range_batch`
      route adopt the same compact per-variant
      `StrategyEvaluationExecution` result — no separate batch-only
      strategy semantics.
- [ ] 4.2 Re-run the N=1/2/4/11 memory/CPU harness from the earlier
      diagnostic pass this session; confirm approximately constant
      memory in N.

## 5. Spec

- [ ] 5.1 `openspec archive compact-strategy-evaluation-boundary-v1`
      after implementation lands, parity is proven, and the acceptance
      criteria in `design.md` are met.
