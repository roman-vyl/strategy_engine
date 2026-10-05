## ADDED Requirements

### Requirement: History policy for the entry-anchored change child

The live history planner SHALL resolve a `change_since_entry` child of a
composite phase condition to an explicit zero entry: no additional bars
beyond the operand's own warm-up, which the existing per-feature
policies already count.

#### Scenario: Entry-anchored child

- **WHEN** a composite phase condition contains a `change_since_entry`
  child on a `4h` feature
- **THEN** the resolved requirements SHALL include an explicit zero
  entry for that child
- **AND** because the open-trade window is anchored at the earlier of
  the plan bar and the entry bar, the anchor value on the entry bar
  SHALL be available.
