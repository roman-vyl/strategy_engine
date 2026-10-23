## ADDED Requirements

### Requirement: Completed candle identity and cost

A completed candle operand SHALL have its own node family whose identity carries the episode identity, the timeframe, the field and
the ATR column. A spec without it SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same completed candle operand
- **THEN** the operand SHALL be computed once per batch per side.
