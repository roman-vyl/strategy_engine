## ADDED Requirements

### Requirement: Impulse ATR identity and cost

An impulse ATR operand SHALL have its own node family whose identity carries the episode identity and the ATR column identity. A
spec without it SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same impulse ATR operand
- **THEN** the operand and its ATR column SHALL each be computed once per batch per side.
