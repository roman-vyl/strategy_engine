## MODIFIED Requirements

### Requirement: Identity twins for predicates and composites

Every predicate, predicate column array, derived operand and composite local node SHALL have a resolve twin that yields its
`NodeSpec` without computing it.

- Labels (`instance_id`, `child_id`, `path_id`) SHALL NOT enter any
  identity.
- A side-free predicate SHALL have an identity without a side.
- A `change` predicate SHALL have its own node family whose identity
  carries `op`, `value` and `lookback` and whose upstream is the
  column node of its operand. It SHALL carry a side only when it has
  a `short` override.
- A segment operand SHALL have its own node family whose identity carries `from`, `to`, `select` and `aggregate`, whose
  upstream is the episode node of the evaluated side and the column node of its series, and which carries the side.
- A ratio operand SHALL have its own node family whose identity carries its sides and whose upstream is the nodes of its
  non-constant sides; it SHALL carry a side when any side does.
- A `range` predicate's identity SHALL carry `bounds` and `empty` only when they differ from their defaults, so the
  identity of every range written before this change is unchanged.

A successful memoized evaluation of any spec containing
`composite_setup` SHALL end with zero `unforeseen_consumptions`.

#### Scenario: Composite in a batch

- **WHEN** a batch contains candidates that differ only in one
  predicate threshold
- **THEN** the shared feature columns, column arrays and unchanged
  children SHALL each be computed once per batch
- **AND** memoized and non-memoized evaluation SHALL produce
  bit-identical outputs.

#### Scenario: Change candidates differing in the threshold

- **WHEN** a batch contains candidates that differ only in the `value` of one `change` predicate
- **THEN** the operand's feature column and its column array SHALL each be computed once per batch.

#### Scenario: Band candidates differing in the bounds

- **WHEN** a batch contains candidates that differ only in `min` or `max` of one range over a ratio of two segments
- **THEN** the MACD columns, both segments and the ratio SHALL each be computed once per batch per side.

## ADDED Requirements

### Requirement: No compute regression without segment or ratio operands

For specs that use no MACD kind, no segment, no ratio and no new range field, evaluation outputs, node identities and
memoized compute counts per node family SHALL be identical to the evaluation before this change.

#### Scenario: Existing parity corpus

- **WHEN** the existing memo compute-count and node-identity tests run after this change
- **THEN** they SHALL pass unchanged.
