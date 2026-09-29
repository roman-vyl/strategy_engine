## Why

Research Service's historical batch backtest resolves managed-policy
exits by calling Strategy Engine's `POST
/v1/strategy-evaluations/managed-replay` once per **opened trade**
(`research_service/execution/managed_policy.py`,
`materialize_backtest_projection.py::_managed_provider`,
`execution/loop.py::_resolve_managed_timeline`). Each call independently
re-validates the strategy spec, rebuilds the feature plan, and
re-evaluates every indicator over the full market range
(`strategy_engine/strategies/application/evaluate_managed_replay.py`:
`ValidateStrategySpec` -> `BuildStrategyFeaturePlan` ->
`EvaluateIndicatorRange`), even though `/range-batch` already computes
the same indicators once per candidate. Measured cost class:
O(candidates x trades x full-range-feature-evaluation) instead of
`/range-batch`'s O(candidates x full-range-feature-evaluation); a
138-candidate/64,548-trade managed batch was estimated at ~17 days and
had to be aborted.

This is not a regression to patch — it is the deliberate per-position
replay design from the Research/Strategy Engine service split
(`docs/15_execution_boundary_audit.md`,
`docs/19_unified_strategy_research_seam_contract.md`), whose cost was
never measured against realistic historical trade counts. Root cause is
fully diagnosed (forensic audit, this session, verified file:line
against both services and the pre-split monolith reference at
`.Trash/legacy_source/bbb/research/strategies/ema_pullback/`, which
computed its feature dataframe once per candidate and ran one
chronological execution loop over all trades). This proposal formalizes
the already-agreed fix design; it does not re-open root-cause
investigation.

## What Changes

- Strategy Engine's candidate-wide evaluation lifetime (the one
  `/range-batch` already uses) gains a new, optional projection —
  `HistoricalManagedProjection` — computed once per candidate whenever
  `exit_management.mode == "managed"`: pre-confirm boolean conditions
  (both sides), fully parameterized derived distances (multiplier
  already applied), and a distilled, ordered `rules[]` description of
  phase transitions and generic take/stop/exit actions. All IDs
  (`condition_id`, `distance_id`, `rule_id`) are opaque to Research —
  Research never interprets `component_id` or strategy parameters.
- Research Service's historical managed-batch path stops calling
  `/managed-replay` once per opened trade. Instead it combines the
  candidate-wide projection (received once, alongside the existing
  `/range-batch` response) with the real per-trade state it already
  owns (entry price/index/side, running MFE/MAE, bars-since-entry,
  active phase/stop/take state) through new, strategy-agnostic managed
  lifecycle primitives, including a generic entry-anchored
  `confirm_bars` sustain-window evaluator (verified in `managed.py` to
  be entry-anchored, not globally precomputable, so it must run
  Research-side against the real `entry_index`).
- A new purpose-built vectorized condition/distance evaluator is added
  Strategy Engine-side, mirroring `managed.py`'s exact per-component
  formulas. It does **not** reuse `exits.py`'s `_signal_rule`/
  `_distance` — verified by direct code diff that those implement
  different comparison operators and different/absent confirm-bars
  semantics for the overlapping component ids (`rsi_signal_exit`,
  `ema_cross_loss_exit`).
- **BREAKING**: none. `POST /v1/strategy-evaluations/managed-replay`
  and the live/single-open-trade projection path
  (`evaluate_start_after_entry_managed_projection`) are unchanged and
  remain the parity oracle during migration.

## Capabilities

### New Capabilities
- `historical-managed-projection-v1`: candidate-wide, once-per-candidate
  projection of managed-policy market conditions and distances from
  Strategy Engine to Research Service, and the Research-side generic
  managed lifecycle primitives that consume it, replacing per-trade
  `/managed-replay` calls in the historical batch path.

### Modified Capabilities
- `ema-pullback-managed-policy-v1`: adds the requirement that a
  candidate-wide `HistoricalManagedProjection` be derivable from the
  same phase-rule/runtime-exit/stop-management/take-management formulas
  `managed.py` already implements, with semantic parity against the
  existing per-trade replay as the acceptance bar. Does not change the
  live replay's own required inputs/behavior (already governed by the
  concurrently in-progress `strategy-evaluation-canonical-boundary-v1`
  envelope-canonicalization change — no overlap: that change modifies
  the "Required inputs" requirement; this change adds a new,
  independent requirement).
- `strategy-research-execution-contract-v1`: adds
  `HistoricalManagedProjection` as an optional field alongside the
  existing per-bar decision contract, and adds a computational-parity
  requirement (feature-evaluation count per candidate independent of
  historical trade count). Does not modify the "Versioned per-bar
  decision contract" requirement text itself (already governed by the
  concurrent envelope-canonicalization change) — this is an additive
  requirement.

## Impact

- `strategy_engine/strategies/contracts.py` — extend
  `HistoricalExecutionProjection` with an optional
  `HistoricalManagedProjection` field.
- `strategy_engine/strategies/ema_pullback/` — new vectorized managed
  condition/distance evaluator (new module); `feature_plan.py`
  unchanged (already plans the needed indicators);
  `application/evaluate_managed_replay.py` and `managed.py` unchanged
  (remain the live path and parity oracle).
- `research_service/execution/managed_policy.py`,
  `execution/loop.py`, `application/backtests/
  materialize_backtest_projection.py` — historical managed path
  switches its projection source from per-trade `/managed-replay`
  HTTP calls to the candidate-wide projection already present in the
  `/range-batch`-equivalent response; new generic managed lifecycle
  primitives (phase advancement, confirm-bars window, stop/take state)
  added. `execution/unified_exits.py` arbitration priority table is
  unchanged.
- No change to any live/runtime code path, no change to
  `/managed-replay`'s own request/response shape, no multiprocessing,
  no strategy-specific special-casing.
