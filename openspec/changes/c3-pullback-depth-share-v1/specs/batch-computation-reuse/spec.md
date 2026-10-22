## ADDED Requirements

### Requirement: Pullback depth identity and cost

A pullback depth operand SHALL have its own node family whose identity carries the episode identity. It SHALL be computed only on
bars with a valid wave. A spec without it SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the pullback depth operand
- **THEN** the operand SHALL be computed once per batch per side.
