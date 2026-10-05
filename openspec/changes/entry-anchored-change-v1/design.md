## Context

The managed pipeline is: features → predicates (market masks) → `composite_phase_condition` (market and trade children by
paths) → phases → stop, take and runtime actions. Market children are evaluated once over the whole frame and folded into one
mask per path (`managed_composite.fold_phase_paths`). Trade children (`bars_in_trade`, `mfe_pct`, `mfe_atr`, `mfe_r`) depend on
the trade and are evaluated per bar: by `managed._phase_met` in single-trade evaluation, and through `distance_id` +
`trade_metric` thresholds in the historical projection (`historical_managed_projection._composite_paths`).

`change {operand, lookback, op, value}` (`predicates.Change`) compares two points of one aligned column, `lookback` bars of the
operand's timeframe apart. Both points are market data, so it is a predicate.

## Goals / Non-Goals

Goals:

- compare the current value of a feature with its value on the trade's entry bar;
- reuse the existing operand grammar, feature planning, column alignment and composite paths;
- no cost for specs that do not use it.

Non-goals:

- a general per-trade state or memory mechanism;
- anchors other than the entry bar (a phase-entry bar, a fixed time);
- a `short` override, atomic phase-rule placement, temporal wrapping.

## Decisions

### D1. A trade atom, not a predicate class

The anchor depends on the trade, so the child is not a market series and cannot be a mask of the predicate layer
(`pre-entry-predicates-v1` stays market-only). It is added as one more trade atom of `composite_phase_condition`, next to
`mfe_r`. The fold already treats every non-market atom as a trade child, so `require`, `at_least` and mixed `at_least` work
without changes to the fold or to `composite_met`.

Alternative rejected: `change {operand, since: "entry", op, value}` in the predicate layer. It would make a predicate
trade-dependent, invalid in `composite_setup` and under `temporal`, and the fold would have to classify predicates by field.

### D2. Name and params

`change_since_entry {operand, op, value}`.

- `operand` uses `predicates._operand` and must be a `feature` (as for `change`). The feature reference is validated by the
  canonical feature-kind contract (`plan_feature_request`).
- `op` in `>=`, `>`, `<=`, `<`; `value` finite, any sign.
- Unknown fields, `lookback`, `short`, a price or constant operand, `==`, `!=` are rejected at static validation
  (`static_semantics`), as the other atom params are.

### D3. Anchor and alignment

`operand(x)` is the operand's column on base bar `x`, the same aligned column a predicate reads
(`align_completed_to_base`: a higher-timeframe bar is visible from its close). The anchor is `operand(e)` where `e` is the
trade's entry bar: `entry_index` in single-trade evaluation, the entry fill bar for a consumer of the projection. The entry fill
happens on the signal bar's close, so `operand(e)` is known at entry and there is no look-ahead.

For a higher-timeframe operand the anchor is the last completed bar of that timeframe at entry, and the difference changes
only when a new bar of that timeframe completes.

On the entry bar the difference is 0, so `>= 0` is true there. The historical start (offset 0) evaluates the entry bar; the
live start (offset 1) starts at `e + 1` but uses the same anchor `operand(e)`.

### D4. Non-finite

The child is False on a bar if `operand(i)` or `operand(e)` is missing or non-finite. A non-finite anchor therefore keeps
the child False for the whole trade. There is no negation, so a not-ready child never makes a path true.

### D5. Side

Side-free: the same `op` and `value` for long and short, like a predicate without override. A side-relative condition is
built in the path from existing children, e.g. a `compare` of two features with a `short` override that swaps the operands.
A `short` override can be added later as a separate change; the wire term would then carry per-side `op` and `value`.

### D6. Placement

Accepted only as a child `condition` of `composite_phase_condition`. A top-level phase rule with
`component_id: change_since_entry` is rejected: the projection keeps atomic rules in their existing forms and the new term
lives only in the `paths` variant. A single-child, single-path composite is the atomic form.

### D7. Projection wire

New contract `ManagedTransitionEntryChange {series_id, op, value}` with `op` a closed enum of the four operators.

- `ManagedTransitionPath` gains `entry_changes: tuple[ManagedTransitionEntryChange, ...] = ()`, the `change_since_entry`
  children in the path's `require`, in declared order. A path is true only if each holds.
- `ManagedTransitionTerm` gains `entry_change: ManagedTransitionEntryChange | None = None`; a term then carries exactly one of
  `condition_id`, (`distance_id`, `trade_metric`) or `entry_change`.
- The series is stored in the existing `distances` map under an opaque id, one per child however many paths reference it,
  with NaN where the operand is not finite (serialized as `null`, as all distances are).
- Serialization omits `entry_changes` when empty and `entry_change` when `None`, so the projection of a candidate without the
  atom is byte-identical.

Consumer evaluation per trade: read `anchor = series[entry_index]` once; on bar `i`, the term holds iff both values are finite
and `series[i] − anchor <op> value`. Cost per bar is one lookup and one comparison, the same as a threshold.

Alternative rejected: encoding the child as a `ManagedTransitionThreshold` with a new `trade_metric`. A threshold compares a
consumer-owned quantity with a per-bar series using `>=`; the anchored difference needs the series itself, an operator and a
constant, and would require an encoding trick the consumer would have to know.

### D8. Single-trade evaluation

`composite_met` passes trade children to `_phase_met`. `_phase_met` gains a `change_since_entry` branch that reads the operand
column through the existing `SeriesCache` at `state.entry_index` and at `index`. The column is converted once per evaluation;
no new trade-state field is needed.

### D9. Planning, identity and cost

- Feature plan: the operand joins the predicate features of composite phase condition children (planned last, with the
  existing collision check). A spec without the atom plans exactly as before.
- Identity: the atom is not a predicate node. Its column is read through the existing per-projection `SeriesCache`, as
  the existing market and trade atoms read theirs; no new memo node family and no change to `resolve_managed_predicates`.
- Cost with the atom: one column conversion per candidate and O(1) work per trade bar. Without the atom: no change.

### D10. Live history

Zero additional bars. The operand's warm-up is counted by the existing per-feature policies; the open-trade window is anchored
at the earlier of the plan bar and the entry bar, so the entry bar is in the frame. The planner records an explicit zero entry
and fails closed on an unknown atom, as today.

## Risks / Trade-offs

- A consumer that does not know the new term cannot execute a spec with this atom. It must reject such a projection, not
  ignore the term. Specs without the atom are unaffected.
- The anchor is the entry bar's aligned value. A spec that wants the value of a bar before entry needs a different anchor;
  out of scope.
