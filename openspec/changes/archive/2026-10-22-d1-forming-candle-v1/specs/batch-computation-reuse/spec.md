## ADDED Requirements

### Requirement: Forming candle identity and cost

A forming candle operand SHALL have its own node family whose identity carries the episode identity, the timeframe and the ATR
column. A spec without it SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same forming candle operand
- **THEN** the operand SHALL be computed once per batch per side.
