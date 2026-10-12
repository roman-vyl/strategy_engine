## ADDED Requirements

### Requirement: Leg mean operand identity and sharing

A leg mean operand SHALL have its own node family whose identity carries the episode identity, the leg and the field, and whose
upstream is the episode and the market bars. Labels SHALL NOT enter the identity.

#### Scenario: Band candidates share the operands

- **WHEN** a batch contains candidates that differ only in `min` or `max` of one range over a ratio of two leg mean operands
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.

### Requirement: Leg mean cost

A leg mean operand SHALL cost O(n) per series, independent of leg length. A spec without a leg mean operand SHALL have the same
node set and the same results as before this change.

#### Scenario: No compute regression

- **WHEN** a spec has no leg mean operand
- **THEN** no leg mean node SHALL be created and no extra work done.
