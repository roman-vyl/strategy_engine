## ADDED Requirements

### Requirement: Partial take distances use the canonical plan

An `atr_partial_take` rule SHALL plan its ATR distance exactly like an
`atr_take_profit` rule with the same `distance`: through the same
canonical exit-distance planning, ATR feature sharing by label and
fail-closed label-collision check. A `pct_partial_take` rule SHALL plan
no features.

For a spec without partial take rules, the plan (features, order and
`plan_hash`) SHALL be unchanged.

#### Scenario: Shared ATR column

- **WHEN** an `atr_partial_take` and an `atr_stop_loss` both use base
  timeframe and period 14
- **THEN** the plan SHALL contain one ATR feature for (base, 14).

#### Scenario: Pct partial take plans nothing

- **WHEN** the only change to a spec is an added `pct_partial_take`
- **THEN** its planned features SHALL equal those of the spec without
  that rule.

#### Scenario: Plan unchanged without partial takes

- **WHEN** a spec has no partial take rules
- **THEN** its `plan_hash` SHALL equal the `plan_hash` produced before
  this change.
