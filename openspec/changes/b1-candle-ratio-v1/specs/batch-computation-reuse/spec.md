## ADDED Requirements

### Requirement: Candle operand identity and sharing

A candle operand SHALL have its own node family whose identity carries the episode identity, the leg, the timeframe, the
direction and the identity of the ATR column, and whose upstream is the episode, the market bars and that ATR column. Labels
SHALL NOT enter the identity.

#### Scenario: Band candidates share the operand

- **WHEN** a batch contains candidates that differ only in `min` or `max` of one range over a ratio of two candle operands
- **THEN** the ATR column, both candle operands and the ratio SHALL each be computed once per batch per side.

### Requirement: Candle operand cost

A candle operand SHALL cost O(n) per series, independent of leg length and of the timeframe. A spec without a candle operand
SHALL have the same node set and the same results as before this change.

#### Scenario: No compute regression without candle operands

- **WHEN** a spec has no candle operand
- **THEN** no candle node SHALL be created and no extra work done.
