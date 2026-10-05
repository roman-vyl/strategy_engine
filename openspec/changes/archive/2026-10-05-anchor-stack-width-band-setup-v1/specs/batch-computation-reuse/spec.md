## ADDED Requirements

### Requirement: Identity of the anchor stack width band setup

`anchor_stack_width_band_setup` SHALL be resolved into two side-free
node families, each with a resolve twin:

- a width node whose identity carries no parameters and whose
  upstream is the `fast`, `slow` and `atr` feature nodes;
- a local node whose identity carries `min_width_atr`, and
  `max_width_atr` only when present, both normalized to floating
  point, and whose upstream is the width node.

Labels (`instance_id`, `child_id`) SHALL NOT enter either identity.
The node identities of `anchor_stack_width_setup` SHALL be unchanged.

#### Scenario: Candidates differing only in the band

- **WHEN** a batch contains candidates that differ only in
  `min_width_atr` or `max_width_atr`
- **THEN** the width node SHALL be computed once per batch
- **AND** memoized and non-memoized evaluation SHALL produce
  bit-identical outputs
- **AND** the memoized evaluation SHALL end with zero
  `unforeseen_consumptions`.

#### Scenario: Equivalent bounds share identity

- **WHEN** one candidate sets `min_width_atr` to `5` and another to
  `5.0`
- **THEN** their local nodes SHALL have the same identity.

### Requirement: No compute regression without the anchor stack width band setup

For specs without `anchor_stack_width_band_setup`, evaluation outputs,
memoized compute counts per node family and node identities SHALL be
identical to the evaluation before this change.

#### Scenario: Existing specs

- **WHEN** the existing memo compute-count and identity tests run
  after this change
- **THEN** outputs, compute counts and identities SHALL match their
  pre-change values exactly.
