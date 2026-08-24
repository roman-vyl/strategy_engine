## Context

See proposal.md - Why for the measured profile and root-cause audit. Relevant current structure (`src/strategy_engine/strategies/ema_pullback/managed.py`):

```
_evaluate_managed_replay_core(raw_spec, frame, plan, ...)
    _items(...) x4        -- phase_rules/stop_rules/take_rules/runtime_rules, built once, outside the loop
    for index in range(evaluation_start_index, target_index + 1):   -- T bars
        _update_extremes(...)
        for rule in phase_rules:   _phase_met(...)        -> _feature_value -> _series(frame, output_id)
        for rule in stop_rules:    (break_even_stop/lock_profit_stop, ATR) -> _feature_value -> _series(...)
        for rule in take_rules:    (no series access)
        for rule in runtime_rules: _runtime_signal(...)    -> _series(frame, output_id)  (rsi_signal_exit: 1x; ema_cross_loss_exit: 2x)
        bars.append(ManagedBarDecision(...))
```

`_series(frame, output_id)` (line 237-241) does `frame.series.get(output_id)` (O(1) dict lookup) then `tuple(float(v) for v in values)` -- an O(F) full-length rebuild, where `frame.series[output_id]` is already an immutable `tuple[str | None, ...]` (`FeatureFrame.series: dict[str, tuple[str | None, ...]]`, `indicators/contracts.py`). Every one of the call sites above sits inside the per-bar loop, so the same `output_id` is rebuilt from scratch up to once per bar per rule that reads it.

Call-graph audit (confirmed, not assumed) of `_evaluate_managed_replay_core`'s two callers:
- `evaluate_start_after_entry_managed_projection` (offset=1, `require_managed_mode=False`) <- `EmaPullbackOpenTradeProjectionAdapter.evaluate` (`live_projections/open_trade.py:154`) <- production live OpenTrade path (`EvaluateOpenTradeProjection`).
- `evaluate_managed_replay` (offset=0, `require_managed_mode=True`) <- `EvaluateManagedReplay.execute` (`strategies/application/evaluate_managed_replay.py`) <- HTTP `POST /strategy-evaluations/managed-replay` (`adapters/http/strategy_routes.py:251-260`) -- the Research/Workbench-facing single-trade managed-replay endpoint.
- The bulk Research/Backtest range evaluator (`EmaPullbackRangeEvaluator` / `strategies/application/evaluate_range.py`) does **not** call this core: it explicitly rejects `exit_management.mode="managed"` with the message pointing callers at the managed-replay endpoint instead (`strategies/ema_pullback/evaluator.py:104`). Bulk managed backtest is not an existing capability of this codebase today, so this change cannot and does not claim to accelerate it.

## Goals / Non-Goals

**Goals:**
- Eliminate the confirmed repeated full-series materialization inside the per-bar managed-replay loop.
- Keep the fix inside the single shared managed-replay core so both real callers (live OpenTrade, managed-replay endpoint) benefit automatically, with no path-specific fast path.
- Preserve every observable output of managed replay exactly (see proposal.md Capabilities / this file's Risks section for the parity list).

**Non-Goals:**
- No decomposition of `managed.py` into a `prepare` / `evaluate_bar` / `runner` package split (discussed as a possible future direction, not part of this change -- see Open Questions / deferred-decisions note below).
- No `PreparedManagedContext` type or similar new internal abstraction beyond the cache itself.
- No change to `ManagedTradeState`'s mutation model (still mutated in place across the loop; not made immutable/functional).
- No new bulk managed-backtest application use case.
- No change to `_atr_output_id`'s per-call linear scan of `indicator_plan.features` (identified in the prior audit as a secondary, much smaller-magnitude hotspot) -- out of scope for this change; may be addressed separately if a future profile shows it matters after this fix lands.
- No change to `FeatureFrame`, HTTP contracts, or strategy spec schema.

## Decisions

**1. Lazy per-execution cache, not eager pre-materialization of all series.**
A plain `dict[str, tuple[float | None, ...]]` local to one `_evaluate_managed_replay_core` call, populated on first access per `output_id` (`cache.setdefault(output_id, lambda: _series(frame, output_id))` or an equivalent explicit if-miss-compute-store), threaded into `_feature_value` and the two direct `_series()` call sites in `_runtime_signal`. Rationale: only the `output_id`s a given spec's configured rules actually touch during this replay get materialized (bounded by `S`, the number of unique series actually used -- typically 1-3 for a real spec, far fewer than the full `FeatureFrame.series` dict), with no separate dependency-compilation pass needed to know in advance which ones those are. Alternative considered: eager pre-pass that walks `phase_rules`/`stop_rules`/`runtime_rules` once before the loop and materializes every series any rule might need. Rejected for this change: it requires duplicating the component_id -> output_id resolution logic that already lives inside each per-bar branch (in a second, parallel pre-pass), which is more code, a second place that must be kept in sync with any future rule type, and no better asymptotic result than the lazy cache for this workload.

**2. Cache lives inside `_evaluate_managed_replay_core`'s call frame, not as a module-level or object-level cache.**
A fresh cache is created every call and discarded when the call returns -- no persistence across replay executions, no cross-request sharing, no global state. This matches the existing purity of the function (no I/O, no shared mutable module state today) and avoids any staleness/invalidation concern (a `FeatureFrame` is always fully materialized input to a given call; nothing about it changes mid-call).

**3. No signature or contract change to `evaluate_managed_replay` / `evaluate_start_after_entry_managed_projection`.**
Both public entry points keep their exact current signatures and return types. The cache is entirely internal to `_evaluate_managed_replay_core` and the private helpers it calls (`_feature_value`, `_phase_met`, `_runtime_signal`) -- callers in `open_trade.py` and `evaluate_managed_replay.py` (application service) require zero changes.

**4. `_series()` itself is not removed.**
It remains the single place that knows how to convert a `FeatureFrame` column into the `tuple[float | None, ...]` representation the replay logic consumes; the cache wraps it rather than replacing its logic, keeping the change small and the diff reviewable.

## Risks / Trade-offs

- **[Risk] Cached float representation silently diverges from what fresh `_series()` calls would have produced (e.g. if the code were ever changed to expect a fresh tuple identity, or if `FeatureFrame` values could mutate mid-call).** -> Mitigation: audit of all four current `_series()` call sites (`managed.py:258,355,374,375`) confirmed every one reads the result only via value indexing/slicing (`values[pos]`, `values[start:index+1]`); none does identity (`is`) comparison, and `FeatureFrame` fields are immutable (`frozen=True, slots=True`, tuple-typed). No code depends on `_series()` producing a distinct object on every call. This is stated as a concrete design constraint (see Open Questions) to be re-verified against the exact code at implementation time, not re-derived from scratch.
- **[Risk] Behavior change disguised as a performance fix.** -> Mitigation: the acceptance plan (tasks.md Group 4/5) requires exact before/after parity on every observable field -- final state, every `ManagedPolicyEvent`, every `ManagedBarDecision`, desired stop/take, and the public `OpenTradeProjectionResult` -- not just a smoke check that the code runs.
- **[Trade-off] Lazy cache does not help a hypothetical caller that only ever touches each `output_id` once per replay (no per-bar repeated access).** -> Accepted: the confirmed pathological pattern in the current codebase is repeated per-bar access (up to `T` times per `output_id`); a lazy cache costs nothing extra when access is already single-shot, so there is no regression case, only either a large win (repeated access, the common case today) or a no-op (single access).
- **[Risk] Real-infra performance acceptance (tasks.md Group 5) depends on the same local MDS/DB environment used for the original profile, which may not always be available.** -> Mitigation: acceptance requires the measurement to actually run against real local infrastructure (matching the standard already set by the `bounded-live-calculation-window` change's Group 7); if that environment is genuinely unavailable at acceptance time, this is a blocker to report, not a reason to substitute a synthetic/fake-MDS benchmark.

## Migration Plan

Single-step, no phased rollout needed: this is an internal implementation change behind two existing, unchanged public entry points.

1. Implement the lazy cache inside `_evaluate_managed_replay_core` and route the four existing feature-access call sites through it.
2. Run semantic-parity tests (before/after on identical fixtures) and the real-infra performance benchmark (same scenario as the original profile).
3. Land as a normal merge once parity and performance evidence are recorded; no feature flag needed (behavior-preserving, no external contract change).
4. Rollback: revert the single commit; `_series()` and all call sites return to their pre-change form with no residual state to clean up (nothing persisted outside a single call).

## Open Questions

- The exact cache-population idiom (`dict.setdefault` with a lambda vs. an explicit `if output_id not in cache:` block) is an implementation detail left to tasks.md/implementation time -- either is behavior-equivalent and does not change the design.
- Whether to also address `_atr_output_id`'s per-call linear scan (identified as a secondary, much smaller hotspot in the prior audit) in this same change or defer it entirely: **deferred** per proposal/design Non-Goals -- if the post-cache real-infra benchmark (Group 5) shows it is no longer negligible, that would be scoped as a follow-up, not folded in here without a fresh decision.
- Future internal decomposition (`prepare_managed_evaluation` / `evaluate_managed_bar` / `run_managed_replay`, discussed with the owner as a possible future direction) is explicitly not designed or scheduled here. It remains a candidate only if the post-cache benchmark shows managed replay is still a dominant cost after this fix -- a decision to be made from that evidence, not now.
