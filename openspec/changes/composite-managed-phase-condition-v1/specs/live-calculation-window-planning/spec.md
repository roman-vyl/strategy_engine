## ADDED Requirements

### Requirement: History policy for composite phase condition children

The live history planner SHALL resolve `composite_phase_condition` by
recursing into its children:

- **Predicate children** SHALL contribute exactly what the same
  predicate contributes as a `composite_setup` child: an explicit zero
  entry for compare, range and state, and `bars − 1` additional base
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
