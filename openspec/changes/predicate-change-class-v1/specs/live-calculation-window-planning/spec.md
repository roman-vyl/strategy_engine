## MODIFIED Requirements

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
  bars on top of their inner predicate.
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
- **THEN** the resolved requirements SHALL include 11 additional base bars and 3 additional `1h` bars for that predicate.

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
