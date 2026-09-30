## ADDED Requirements

### Requirement: History policy for composite setup children

The live history planner SHALL resolve `composite_setup` by recursing
into its children:

- **Semantic setup children** SHALL contribute exactly the requirement
  their existing component policy contributes.
- **Non-temporal predicates** SHALL contribute an explicit
  zero-additional-history entry; their indicator warm-up is already
  counted from the plan.
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
