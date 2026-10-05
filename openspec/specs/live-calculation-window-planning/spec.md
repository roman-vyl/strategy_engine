# live-calculation-window-planning Specification

## Purpose
Compute, without any I/O, a bounded history start timestamp that is sufficient, under a set of configured indicator-convergence and strategy-semantic warm-up policies, to evaluate a given live strategy spec at a target bar — so the live acquisition path stops reading history that scales with total accumulated market-data depth.
## Requirements
### Requirement: Pure history-start planning

The planner SHALL compute a bounded history start (`from_ms`) from a strategy spec's indicator plan, the base timeframe, the strategy's event/lookback requirements, and a caller-supplied history anchor timestamp.

The planner SHALL NOT perform any market-data read, HTTP call, or candle-frame computation, and SHALL NOT select the history anchor itself.

#### Scenario: Planner given spec, indicator plan, base timeframe, and anchor

- **WHEN** the planner is invoked with a validated strategy spec, its indicator plan, the base timeframe, and a history anchor timestamp
- **THEN** the planner SHALL return a required history start at or before the anchor
- **AND** SHALL NOT issue any market-data or candle request while doing so.

### Requirement: Combine indicator and strategy-component history requirements additively

The planner SHALL derive per-timeframe history requirements from two sources: generic indicator warm-up requirements resolved from the indicator plan, and strategy-specific event/lookback requirements resolved from the strategy spec's contexts, blockers, setups, triggers, and risk/entry/exit components.

Because strategy components consume already-computed indicator series rather than raw candles, the planner SHALL NOT combine these two sources by taking their maximum. It SHALL instead sum the maximum indicator warm-up span with the maximum strategy-semantic span:

```text
required_pre_anchor_span = indicator_warmup_span + strategy_semantic_span
from_ms = anchor - required_pre_anchor_span
```

The planner SHALL identify, for diagnostics, which single requirement contributed the largest span within each of the two sources, as two separately typed fields (a winning indicator requirement and a winning strategy-semantic requirement), not as a single field whose source category must be inferred from requirement text.

Strategy-component lookback counts SHALL use the bar axis on which the existing component implementation actually iterates. For currently live-supported `ema_pullback` components this is the base FeatureFrame axis (after HTF indicator alignment), not the timeframe axis of whichever indicator feeds the component. A component SHALL only use a different axis if it explicitly defines one.

#### Scenario: Strategy component consumes an indicator series

- **WHEN** the spec includes an indicator with a resolved warm-up span and a strategy component with a resolved semantic lookback that reads that indicator's already-computed values
- **THEN** the planner SHALL ensure the component's lookback window falls entirely after the indicator's own warm-up region
- **AND** SHALL NOT produce a `from_ms` that leaves any part of the component's lookback window backed by not-yet-valid indicator values.

#### Scenario: Multiple requirements at different timeframes

- **WHEN** the spec includes both an indicator with a multi-timeframe convergence warm-up and a strategy setup with a fixed bar lookback
- **THEN** the planner SHALL evaluate the required span implied by each requirement within its source category
- **AND** SHALL sum the largest indicator span with the largest strategy-semantic span to produce `from_ms`
- **AND** SHALL identify the winning indicator requirement and the winning strategy-semantic requirement as separate outputs.

#### Scenario: Strategy component's indicator does not match the component's own axis

- **WHEN** a strategy component reads an indicator computed on a higher timeframe (e.g. a blocker reading a `1h` RSI) but the component itself is evaluated on the base FeatureFrame axis
- **THEN** the component's semantic lookback SHALL be counted in base FeatureFrame bars
- **AND** SHALL NOT be multiplied by the `1h` indicator's timeframe duration.

### Requirement: Recursive indicator convergence warm-up

For indicators computed recursively (where a fixed bar count does not fully bound the influence of prior history), the planner SHALL use a convergence warm-up: a history length long enough that the influence of an arbitrary initial seed value falls below a fixed tolerance by the target bar.

For an exponential-moving-average-style indicator with smoothing factor `alpha`, the seed influence after `n` bars decays as `(1-alpha)^n`; the warm-up requirement SHALL be derived from `(1-alpha)^n < tolerance`, not from `alpha^n`.

The Wilder-smoothed ADX/DI cascade (recursive smoothing of TR/+DM/-DM followed by a second recursive smoothing pass to produce ADX) SHALL be resolved as its own recursive requirement, using Wilder's decay factor, independently from the exponential-moving-average policy above.

Indicators whose full history dependence is bounded by a fixed bar count (no recursive seed-influence term) SHALL be resolved as finite-window requirements instead.

#### Scenario: EMA-based indicator in the spec

- **WHEN** the indicator plan includes an exponential-moving-average-style indicator
- **THEN** the resolved requirement SHALL express a bar count sufficient for `(1-alpha)^n` to fall below the fixed tolerance
- **AND** SHALL NOT treat the indicator's period alone as sufficient history.

#### Scenario: ADX/DMI indicator in the spec

- **WHEN** the indicator plan includes the Wilder-smoothed ADX/DI indicator
- **THEN** the resolved requirement SHALL be derived from Wilder's recursive smoothing decay, evaluated independently from the exponential-moving-average tolerance policy
- **AND** SHALL NOT be classified as a finite-window requirement.

#### Scenario: Finite-window indicator in the spec

- **WHEN** the indicator plan includes an indicator whose value at a bar depends only on a fixed preceding bar count
- **THEN** the resolved requirement SHALL be that fixed bar count
- **AND** SHALL NOT apply a convergence-tolerance calculation.

### Requirement: Timeframe-aware requirements with complete leading HTF bucket for every HTF in use

Each history requirement SHALL be expressed as a `(timeframe, bars)` pair. The planner SHALL convert higher-timeframe requirements into base-timeframe history span using a fixed per-timeframe candle duration and the supplied base timeframe.

For every higher timeframe actually present in the indicator plan, the planner SHALL roll the resulting `from_ms` back to the start of that timeframe's fixed-duration UTC resample bucket, using the same boundary alignment semantics as the existing pandas resample step (e.g. `4h` buckets start at `00:00, 04:00, 08:00, ...` UTC; a candidate `from_ms` of `06:35` for a `4h` requirement SHALL be rolled back to `04:00`). This alignment SHALL be applied for each distinct higher timeframe the plan uses, not only for the timeframe of the single largest requirement — satisfying alignment for one higher timeframe SHALL NOT be assumed to satisfy it for another.

Calendar gaps and trading-session boundaries are out of scope for this requirement; the fixed-duration conversion assumes continuously traded instruments.

#### Scenario: Higher-timeframe requirement present

- **WHEN** a requirement specifies a timeframe higher than the base timeframe
- **THEN** the planner SHALL convert it to an equivalent base-timeframe history span using fixed candle durations
- **AND** SHALL include that span when computing `from_ms`.

#### Scenario: Computed from_ms does not land on an HTF bucket boundary

- **WHEN** the computed `from_ms` for a higher-timeframe requirement falls inside that timeframe's resample bucket rather than at its start
- **THEN** the planner SHALL move `from_ms` back to the start of that bucket, using the same fixed-duration UTC boundary the existing resample step uses
- **AND** the resulting range SHALL back a complete leading higher-timeframe candle when passed through the existing resample step.

#### Scenario: Multiple higher timeframes used simultaneously

- **WHEN** the indicator plan uses more than one higher timeframe (e.g. both `1h` and `4h`)
- **THEN** the planner SHALL align `from_ms` to a bucket boundary for every one of those higher timeframes simultaneously
- **AND** SHALL NOT return a `from_ms` that is bucket-aligned for only one of them.

### Requirement: Fail closed on unrecognized components

Every indicator kind present in the indicator plan and every live-supported strategy context/blocker/setup/trigger/risk/exit component SHALL have an explicit history policy, including components that require zero additional history beyond an upstream dependency.

An indicator kind or strategy component with no registered history policy SHALL cause the planner to fail rather than silently contribute zero required history.

#### Scenario: Indicator plan contains an unrecognized indicator kind

- **WHEN** the indicator plan contains an indicator kind with no registered history policy
- **THEN** the planner SHALL fail closed
- **AND** SHALL NOT silently treat the unrecognized kind as requiring zero history.

#### Scenario: Component with no independent requirement

- **WHEN** a planned feature or strategy component depends only on an already-required upstream indicator and adds no lookback of its own
- **THEN** it SHALL be recorded as an explicit zero-additional-warm-up entry
- **AND** SHALL NOT be omitted from the resolved requirement set.

### Requirement: Diagnostic output with explicit winning-requirement fields

The planner's result SHALL include the computed `from_ms`, a `winning_indicator_requirement` field naming the requirement contributing the largest indicator-warm-up span, a `winning_strategy_requirement` field naming the requirement contributing the largest strategy-semantic span, and the full set of evaluated requirements, so callers can log and a parity/performance harness can attribute the required window to specific components.

The result SHALL NOT rely on a single combined "winning requirement" field, and callers SHALL NOT be required to inspect a requirement's `reason` text to determine whether it belongs to the indicator or strategy-semantic source category.

#### Scenario: Planner result consumed for diagnostics

- **WHEN** a caller requests the planner's result
- **THEN** the result SHALL expose `winning_indicator_requirement`, `winning_strategy_requirement`, and the complete requirement set as distinct fields
- **AND** SHALL NOT require re-deriving indicator or strategy requirements, or parsing free text, to explain the chosen `from_ms`.

### Requirement: Bounded-sufficient, not minimal, semantics for stateful components

For strategy components whose semantic memory is not bounded by any fixed lookback (e.g. a component that accumulates state across an open-ended trend episode), the planner SHALL apply a conservative, fixed, configured bounded warm-up rather than claiming a mathematically minimal or provably exact history requirement.

This capability's outputs SHALL be described and consumed as "bounded, policy-sufficient" history, validated by parity testing, not as "minimal, correct" history.

#### Scenario: Stateful strategy component in the spec

- **WHEN** the spec includes a strategy component whose state is not bounded by a fixed lookback
- **THEN** the planner SHALL apply that component's configured conservative bounded warm-up
- **AND** SHALL NOT claim the resulting `from_ms` is the provably minimal history required for identical output to a full-history calculation.

### Requirement: History policy for composite setup children

The live history planner SHALL resolve `composite_setup` by recursing
into its children:

- **Semantic setup children** SHALL contribute exactly the requirement
  their existing component policy contributes.
- **Predicates that read the current bar only** (`compare`, `range`,
  `state`) SHALL contribute an explicit zero-additional-history entry;
  their indicator warm-up is already counted from the plan.
- **`change` predicates** SHALL contribute `lookback` additional bars
  of the operand's timeframe on top of the operand's own warm-up,
  converted to base bars by the existing timeframe-aware conversion.
- **Temporal predicates** SHALL contribute `bars − 1` additional base
  bars on top of their inner predicate. Over a `change` predicate the
  window SHALL be counted in bars of the operand's timeframe, so that the
  requirement is a sufficient bound on one axis (such a bar is never
  shorter than a base bar).
- **An unrecognized child, predicate class or mode** SHALL make the
  planner fail closed.

#### Scenario: Temporal window on a higher-timeframe condition

- **WHEN** a composite contains `held_for 36` over a `state` predicate
  on a `1h` context
- **THEN** the resolved requirements SHALL include 35 additional base
  bars for that predicate
- **AND** the `1h` provider EMA warm-up SHALL be counted by the
  existing per-feature policy.

#### Scenario: Unknown predicate class

- **WHEN** a composite child carries a predicate class with no history
  policy
- **THEN** the planner SHALL fail closed.

#### Scenario: Change on a higher-timeframe feature

- **WHEN** a composite child is a `change` predicate on a `1h` feature with `lookback` 3
- **THEN** the resolved requirements SHALL include 3 additional `1h` bars for that predicate
- **AND** the feature's own warm-up SHALL be counted by the existing per-feature policy.

#### Scenario: Temporal window over a change

- **WHEN** a composite child is `held_for 12` over a `change` predicate with `lookback` 3 on a `1h` feature
- **THEN** the resolved requirements SHALL include 14 additional `1h` bars (3 + 12 − 1) for that predicate, a sufficient bound for
  the 11 base-bar window on top of 3 `1h` bars.

### Requirement: History policy for composite phase condition children

The live history planner SHALL resolve `composite_phase_condition` by
recursing into its children:

- **Predicate children** SHALL contribute exactly what the same
  predicate contributes as a `composite_setup` child: an explicit zero
  entry for compare, range and state, `lookback` additional bars of
  the operand's timeframe for change, and `bars − 1` additional base
  bars on top of the inner predicate for temporal.
- **Atom children** SHALL contribute the explicit zero entry of their
  existing phase-rule policy.
- **An unrecognized child, atom, predicate class or mode** SHALL make
  the planner fail closed.

#### Scenario: Temporal child before the entry

- **WHEN** a composite phase condition contains `held_for 12` over a
  compare predicate
- **THEN** the resolved requirements SHALL include 11 additional base
  bars for that child
- **AND** because the open-trade window is anchored at the earlier of
  the plan bar and the entry bar, the window SHALL be available on the
  entry bar.

#### Scenario: Change child before the entry

- **WHEN** a composite phase condition contains a `change` predicate on a `1h` feature with `lookback` 3
- **THEN** the resolved requirements SHALL include 3 additional `1h` bars for that child
- **AND** the open-trade window anchoring SHALL apply as for any other predicate child.

### Requirement: History policy for partial take components

The live history planner SHALL register `pct_partial_take` and
`atr_partial_take` as exit components with an explicit
zero-additional-warm-up entry. The ATR history of `atr_partial_take`
SHALL come from its planned ATR feature, as for `atr_take_profit`.

#### Scenario: Spec with an ATR partial take

- **WHEN** the planner resolves a spec containing an `atr_partial_take`
- **THEN** the resolved requirements SHALL include an explicit zero
  entry for that component
- **AND** the planner SHALL NOT fail closed on it.

#### Scenario: Requirements unchanged without partial takes

- **WHEN** a spec has no partial take rules
- **THEN** its resolved history requirements SHALL equal those before
  this change.

