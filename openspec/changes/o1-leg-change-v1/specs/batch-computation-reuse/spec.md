## ADDED Requirements

### Requirement: Leg change identity and cost

A leg change operand SHALL have its own node family whose identity carries the episode identity, the leg, the field and the touch.
A spec without it SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same leg change operand
- **THEN** the operand SHALL be computed once per batch per side.
