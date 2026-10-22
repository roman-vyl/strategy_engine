## ADDED Requirements

### Requirement: Leg top mean identity and cost

A leg top mean operand SHALL have its own node family whose identity carries the episode identity, the leg, the field and the
share. Its impulse value SHALL be computed once per touch and its pullback value only on bars with a valid wave. A spec without it
SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level over a ratio of two leg top mean operands
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.
