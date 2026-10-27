## ADDED Requirements

### Requirement: Difference identity and cost

A difference SHALL have its own node family whose upstream is its two sides' nodes. A spec without it SHALL have the same node set
and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same difference
- **THEN** the difference and its sides SHALL each be computed once per batch per side.
