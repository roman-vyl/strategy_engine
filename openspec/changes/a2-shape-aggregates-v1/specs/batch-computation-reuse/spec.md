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
- A segment operand SHALL have its own node family whose identity carries `from`, `to`, `value`, `window`, `aggregate` and `negate`, whose
  upstream is the episode node of the evaluated side and the column node of its series, and which carries the side. `span`,
  `top` and `eligibility` SHALL enter the identity only when set, so every segment written before this change keeps its identity.
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
- **THEN** the EMA columns, both segments and the ratio SHALL each be computed once per batch per side.

#### Scenario: Branch candidates differing only in the bounds

- **WHEN** a batch contains candidates that differ only in `min` or `max` of the range of one A2 branch
- **THEN** the EMA columns, both segments and the ratio of that branch SHALL each be computed once per batch per side.

## ADDED Requirements

### Requirement: Segment aggregate cost

`sum`, `mean_per_bar` and `abs_sum` SHALL cost O(n) per series. `max` and `min` SHALL cost at most O(n log n) per
(series, span) and O(1) per bar, independent of leg length. `top_abs_sum` SHALL cost at most O(n · `last_n`). A spec without
`span`, `top`, `eligibility` or the new aggregates SHALL evaluate with the compute count and outputs of the evaluation
before this change.

#### Scenario: No regression without the new fields

- **WHEN** a batch contains only A1 band candidates
- **THEN** the number of node computations and the outputs SHALL equal those before this change.
