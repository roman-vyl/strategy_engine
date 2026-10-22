## ADDED Requirements

### Requirement: Leg sum identity and cost

A leg sum operand SHALL have its own node family whose identity carries the episode identity, the leg and the field, with the
episode and the market bars upstream; labels SHALL NOT enter it. It SHALL cost O(n) per series. A spec without a leg sum operand
SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operands

- **WHEN** a batch contains candidates that differ only in a level over a ratio of two leg sum operands
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.
