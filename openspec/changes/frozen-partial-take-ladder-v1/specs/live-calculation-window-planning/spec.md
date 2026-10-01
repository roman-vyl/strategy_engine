## ADDED Requirements

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
