## ADDED Requirements

### Requirement: Anchor follow operand identity and cost

An anchor follow operand SHALL have its own node family whose identity carries the episode identity (and thereby the anchor EMA the
episode is built from) and whose upstream is the episode. Labels SHALL NOT enter the identity. It SHALL cost O(n) per series, independent
of leg length. A spec without an anchor follow operand SHALL have the same node set and the same results as before this change.

#### Scenario: Band candidates share the operand

- **WHEN** a batch contains candidates that differ only in `min` or `max` of one range over an anchor follow operand
- **THEN** the operand SHALL be computed once per batch per side.

#### Scenario: No compute regression

- **WHEN** a spec has no anchor follow operand
- **THEN** no anchor follow node SHALL be created and no extra work done.
