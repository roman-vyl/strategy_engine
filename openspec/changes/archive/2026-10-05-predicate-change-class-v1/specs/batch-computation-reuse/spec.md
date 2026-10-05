## MODIFIED Requirements

### Requirement: Identity twins for predicates and composites

Every predicate, predicate column array and composite local node SHALL have a resolve twin that yields its `NodeSpec` without
computing it.

- Labels (`instance_id`, `child_id`, `path_id`) SHALL NOT enter any
  identity.
- A side-free predicate SHALL have an identity without a side.
- A `change` predicate SHALL have its own node family whose identity
  carries `op`, `value` and `lookback` and whose upstream is the
  column node of its operand. It SHALL carry a side only when it has
  a `short` override.

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
