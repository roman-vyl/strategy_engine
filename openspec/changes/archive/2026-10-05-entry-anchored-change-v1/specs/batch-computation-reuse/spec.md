## ADDED Requirements

### Requirement: No compute regression without the entry-anchored change child

For a spec without a `change_since_entry` child, the following SHALL be
identical to those before this change:

- `plan_hash` and plan labels;
- memoized node identities and compute counts per node family;
- evaluation outputs and the serialized managed projection.

A `change_since_entry` child SHALL NOT introduce a memo node family. Its
operand column SHALL be converted at most once per managed projection
and at most once per single-trade evaluation.

#### Scenario: Existing spec

- **WHEN** a spec with no `change_since_entry` child is evaluated
- **THEN** its `plan_hash`, node identities, compute counts and outputs
  SHALL equal those recorded before this change.

#### Scenario: Shared operand column

- **WHEN** two paths of one composite reference the same
  `change_since_entry` child
- **THEN** the projection SHALL convert its operand column once and emit
  one series for it.
