## ADDED Requirements

### Requirement: Candle force series sharing and cost

The candle force series of a side SHALL be derived once per batch per side and field from the shared market arrays; candidates that
differ only in `min` or `max` of one range over a ratio of two leg mean operands SHALL share both operands and the ratio. A spec
without a force field SHALL have the same node set, identities and results as before this change, and no force series SHALL be built for it.
The cost SHALL be O(n) per series, independent of leg length.

#### Scenario: Band candidates share the operands

- **WHEN** a batch contains candidates that differ only in a bound of one range over a ratio of two force leg means
- **THEN** both operands and the ratio SHALL each be computed once per batch per side.

#### Scenario: No compute regression

- **WHEN** a spec has no force field
- **THEN** no force series SHALL be built and no extra work done.
