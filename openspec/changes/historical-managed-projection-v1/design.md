## Context

See `proposal.md` - Why for the measured cost and root cause. Relevant
current state:

- `/range-batch` already acquires one shared `MarketFrame`/
  `EvaluationContext` per batch request and reuses it across every
  candidate variant — this is the proven-scalable path (8352-candidate
  non-managed batch completed in ~5.5 hours).
- `/managed-replay` is a separate, deliberately "coarse-grained"
  per-**position** endpoint
  (`evaluate_managed_replay.py`) that independently re-validates,
  re-plans, and re-evaluates indicators on every call. It is currently
  invoked once per opened trade by Research's
  `_resolve_managed_timeline`/`_managed_provider`.
  `research_service/execution/managed_policy.py`'s
  `ManagedEffectiveState`/`ManagedPolicyTimeline` structures already
  hold everything Research needs to arbitrate exits locally; only their
  *construction source* changes under this design.
- `managed.py` is the authoritative per-trade state machine: phases
  `("initial_risk", "proven", "protected", "runner", "exhaustion")`,
  `_phase_met()` (conditions: `bars_in_trade`, `mfe_pct`, `mfe_atr`,
  `adx_di_threshold`), `_runtime_signal()` (runtime exits:
  `phase_runtime_exit`, `rsi_signal_exit`, `ema_cross_loss_exit`),
  `stop_management` (`break_even_stop`, `lock_profit_stop`),
  `take_management` (`take_profile_switch`/`disable_fixed_tp`). Every
  one of these 10 components was audited component-by-component this
  session: none requires calling Strategy Engine again after entry —
  each is either purely market-derived (vectorizable once per
  candidate) or purely trade-state-dependent (Research already owns
  the inputs).
- `exits.py`'s `_signal_rule()`/`_distance()` look reusable for the
  overlapping component ids but are proven NOT semantically identical
  to `managed.py` (different comparison operators, different/absent
  confirm-bars window) — see `specs/ema-pullback-managed-policy-v1`
  delta.
- `confirm_bars` is proven entry-anchored by direct code reading of
  `managed.py::_runtime_signal`: `start = index - confirm_bars + 1;
  if start < evaluation_start_index: return False`, where
  `evaluation_start_index` tracks the specific trade's entry. This
  cannot be precomputed as one candidate-wide confirmed series.
- Exit arbitration priority
  (`research_service/execution/unified_exits.py`: `stop_loss(1) >
  managed_stop(2) > take_profit(3) > runtime_protective(4) >
  runtime_take(5) > runtime_close/runtime_exit(6) > signal(7)`) is
  unchanged by this design.
- Precedent: the pre-split BBB monolith
  (`.Trash/legacy_source/bbb/research/strategies/ema_pullback/
  execution/`) computed its feature dataframe once per candidate
  (`backtest.py`) and ran one chronological bar-loop over all trades
  (`managed_execution_loop.py`, `managed_exit_provider.py`) — this
  design restores that cost shape without reverting the service split.

## Goals / Non-Goals

**Goals:**
- Reduce historical managed-batch Strategy Engine calls from O(trades)
  to O(1) per candidate.
- Preserve the RS/SE ownership boundary exactly: SE owns strategy
  semantics/indicator computation/component interpretation; RS owns
  position lifecycle, fills, exit arbitration, accounting.
- Keep `/managed-replay` and the live open-trade projection path fully
  intact, unmodified, and authoritative for live use and as the
  migration parity oracle.

**Non-Goals:**
- Not a general managed-architecture refactor. Not changing how live
  trades are evaluated. Not changing Research's arbitration priority
  table. Not introducing multiprocessing or per-call caching as the
  fix. Not special-casing any one strategy or experiment (e.g. EMA500
  RSI87). Not resolving or merging with the concurrently in-progress
  `strategy-evaluation-canonical-boundary-v1` envelope-canonicalization
  change.

## Decisions

**D1: Extend the existing candidate-wide contract rather than add a new
endpoint.** `HistoricalManagedProjection` rides on the same
`HistoricalExecutionProjection`/range-batch-equivalent response
`/range-batch` already returns once per candidate, rather than a new
HTTP call. Alternative considered: a dedicated
`/managed-projection-batch` endpoint mirroring `/range-batch`'s
lifetime — rejected because it would duplicate the
validate/plan/evaluate pipeline instead of reusing the one `/range-
batch` already runs, and would require Research to correlate two
separate per-candidate responses.

**D2: Wire shape is `conditions` + `distances` + `rules`, all IDs
opaque.** Alternative considered: transport raw indicator series (ADX,
RSI, ATR) and let Research evaluate `managed.py`'s formulas itself —
rejected per the user's explicit ownership constraint: Research must
never interpret `component_id` or strategy parameters, only consume
pre-evaluated booleans/distances/generic instructions. This also avoids
recreating a second, parallel spec-interpretation path Research-side.

**D3: `distances` carry the multiplier pre-applied.** Alternative
considered: transport the bare indicator value and the multiplier
separately, let Research multiply — rejected because it leaks a
strategy parameter (the multiplier) across the boundary; SE already
computes the scaled value internally in `managed.py`, so projecting the
already-scaled distance costs nothing extra and keeps the boundary
clean.

**D4: `confirm_bars` sustain window is applied Research-side as a
generic primitive over the pre-confirm `conditions` series, keyed by
the trade's real `entry_index`.** Alternative considered: SE
precomputes one confirmed-boolean series per candidate — rejected,
proven incorrect: confirmation is entry-anchored (D-verified from
`managed.py` code), so a single candidate-wide confirmed series would
be wrong for every trade whose entry does not align with the series'
implicit anchor. The primitive itself (index arithmetic over a boolean
array and an integer window) is strategy-agnostic, so it belongs in
Research alongside the rest of the generic managed lifecycle logic, not
duplicated per-strategy.

**D5: A new, purpose-built vectorized evaluator on the SE side,
formula-matched to `managed.py`, not a reuse of `exits.py`.** See
Audit 2 finding in `specs/ema-pullback-managed-policy-v1` delta.
Rejected alternative: adapt `_signal_rule`/`_distance` with extra
parameters to cover both semantics — rejected because it would make one
already-shared function branch on caller identity, increasing risk of
silently regressing the static exit-policy path while fixing this one;
a fresh implementation parity-tested against both oracles is safer and
easier to reason about.

**D6: Rules are pre-distilled by SE, not raw `phase_rules`/
`take_management`/`stop_management`/`runtime_exits` structures passed
through.** Research already holds `raw_spec` today (it's the request it
sent) but MUST NOT parse it for managed semantics — doing so would
recreate a second, parallel spec-interpretation path in Research and
reopen the semantic-duplication risk this change exists to close. SE
distills phase order, activation phase, condition/distance references,
`confirm_bars`, and a generic take/stop/exit action enum into `rules[]`
specifically so Research's consumption code has no strategy-specific
branches.

**D6a: `rules[]` is a minimal discriminated union, formalized before
implementation, with exactly four kinds — one per managed-policy
concern `managed.py` implements (phase transition, take action, stop
action, runtime exit).** Every variant carries only opaque references
and generic fields; none ever carries `component_id` or a raw strategy
parameter. Common to every variant: `rule_id` (opaque), `activation_phase`
(the phase in which this rule is evaluated), `confirm_bars` (integer,
applied Research-side per D4), and zero or more `condition_id`/
`distance_id` references (opaque, per D2/D3). The four `kind` values:

- `phase_transition` — advances the trade to a new phase.
  Adds: `target_phase`, `condition_id` (the gating condition).
- `take_action` — mutates take-profit state. Adds: `action` from a
  closed, generic enum (`disable_take_profit` |
  `enable_take_profit`), `condition_id` and/or `distance_id`
  (whichever the rule's gate is expressed in).
- `stop_action` — mutates stop state. Adds: `action` from a closed,
  generic enum (`move_to_breakeven` | `lock_profit`), `distance_id`
  (the stop's new distance).
- `runtime_exit` — signals an exit independent of phase/stop/take
  state. Adds: `exit_class` from a closed, generic enum
  (`runtime_protective` | `runtime_take` | `runtime_close`), matching
  the class names Research's own arbitration table
  (`unified_exits.py`) already uses, `condition_id` (the trigger).

Research SHALL dispatch on `kind` (and, for `take_action`/
`stop_action`/`runtime_exit`, on the closed `action`/`exit_class`
enum) alone — never on `rule_id`, `condition_id`, or `distance_id`
content, and never by inspecting `raw_spec`. This is what makes
Research's consumption code strategy-agnostic: adding a new managed
component on the Strategy Engine side never requires a Research Service
change as long as the new component maps to one of these four kinds.

## Risks / Trade-offs

- [Risk] New vectorized SE-side evaluator diverges subtly from
  `managed.py` for some component/parameter combination not covered by
  the parity corpus → Mitigation: acceptance criterion 1
  (`proposal.md`) requires bar-for-bar, trade-for-trade parity against
  `/managed-replay` as oracle across a corpus covering every managed
  component, not just the triggering RSI87 case; `/managed-replay`
  stays available indefinitely as a live comparison target, not
  deprecated by this change.
- [Risk] Confirm-bars primitive implemented incorrectly Research-side
  (e.g. off-by-one against `managed.py`'s exact `index - confirm_bars +
  1` boundary) → Mitigation: implementation must port the exact
  boundary formula verified in `managed.py::_runtime_signal`, with a
  dedicated unit test asserting the boundary case (trade whose entry
  lands exactly `confirm_bars - 1` bars before a candidate condition
  bar).
- [Risk] Growing the contract's opaque `rules[]` shape becomes a second
  place strategy semantics can drift from `managed.py` as new managed
  components are added later → Mitigation: D6 keeps `rules[]` generic
  (phase/action enum, not per-component branches), and the semantic-
  parity acceptance criterion is a standing requirement, not a one-time
  migration check, so future managed-component additions inherit the
  same parity bar.
- [Trade-off] This adds one more field to an already-complex cross-
  service contract instead of a cleaner rewrite of the managed
  boundary → accepted deliberately per explicit scope: this is a
  narrow historical-transport/evaluation-granularity fix, not a
  managed-architecture refactor.

## Migration Plan

1. Add `HistoricalManagedProjection` to
   `strategy_engine/strategies/contracts.py` as an optional field
   (`None` when `exit_management.mode != "managed"`) — additive, no
   existing consumer breaks.
2. Implement the new vectorized condition/distance/rules evaluator
   Strategy Engine-side; wire it into the existing candidate-wide
   evaluation lifetime `/range-batch` already uses, gated on
   `exit_management.mode == "managed"`.
3. Parity-test the new evaluator against `/managed-replay` across the
   component corpus in `proposal.md` acceptance criterion 1, before any
   Research Service change lands.
4. Add the generic managed lifecycle primitives Research-side (phase
   advancement, entry-anchored confirm-bars window, stop/take state)
   consuming `HistoricalManagedProjection`, alongside — not replacing —
   the existing `/managed-replay`-based path.
5. Switch the historical managed-batch path
   (`materialize_backtest_projection.py::_managed_provider`) to the new
   primitives; run the full acceptance corpus (both criteria) before
   removing the batch path's dependency on `/managed-replay`.
6. `/managed-replay` and the live open-trade projection path are never
   modified or removed by this migration; rollback is simply reverting
   the batch path's provider selection back to the per-trade call.

## Open Questions

None — the design decisions above (D1-D6) were locked with the user
before this OpenSpec change was authored; nothing here is deferred.
