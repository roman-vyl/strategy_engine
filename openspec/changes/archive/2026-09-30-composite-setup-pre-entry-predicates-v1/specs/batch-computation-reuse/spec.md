## ADDED Requirements

### Requirement: Identity twins for predicates and composites

Every predicate, predicate column array and composite local node SHALL have a resolve twin that yields its `NodeSpec` without
computing it.

- Labels (`instance_id`, `child_id`, `path_id`) SHALL NOT enter any
  identity.
- A side-free predicate SHALL have an identity without a side.

A successful memoized evaluation of any spec containing
`composite_setup` SHALL end with zero `unforeseen_consumptions`.

#### Scenario: Composite in a batch

- **WHEN** a batch contains candidates that differ only in one
  predicate threshold
- **THEN** the shared feature columns, column arrays and unchanged
  children SHALL each be computed once per batch
- **AND** memoized and non-memoized evaluation SHALL produce
  bit-identical outputs.

### Requirement: No compute regression for existing specs

For specs without `composite_setup`, the following SHALL be identical
to the evaluation before this change:

- evaluation outputs;
- memoized compute counts per node family;
- node identities.

Wall-clock time on the existing batch benchmark workload SHALL show no
regression beyond measurement noise.

#### Scenario: Existing parity corpus

- **WHEN** the existing parity corpus and memo compute-count tests run
  after this change
- **THEN** outputs and compute counts SHALL match their pre-change
  values exactly.

### Requirement: Feature columns are converted once for predicates

Predicates SHALL read feature values through one memoized float64
array per feature identity per evaluation context. This array SHALL be
shared by all predicates, both sides and all batch candidates.

#### Scenario: Many predicates on one column

- **WHEN** three predicates read the same RSI column on both sides
- **THEN** that column SHALL be converted to an array once.
