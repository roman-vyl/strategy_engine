## ADDED Requirements

### Requirement: Leg speed identity and cost

A leg speed operand SHALL have its own node family whose identity carries the episode identity and the leg. A spec without it SHALL
have the same node set and results as before this change.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level over a ratio of two leg speed operands
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.
