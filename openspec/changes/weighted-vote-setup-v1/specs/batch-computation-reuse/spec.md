## ADDED Requirements

### Requirement: Identity of the weighted vote setup

A `weighted_vote_setup` SHALL be one semantic node under the requirement "Semantic node identity". Its identity SHALL be derived from:

- the node kind `setup.weighted_vote` and its implementation version;
- its normalized local configuration:
  - `threshold` and every `weight` as the exact decimal strings of the requirement "Weight arithmetic";
  - `level` as numbers;
  - `role`, `direction`, the veto flags;
  - `voter_id` and `input_id`, because they name the evidence series;
  - the structure of voters, inputs and steps in declared order, because declared order names `blocked_by`;
- the identities of its upstream nodes: the predicate-layer nodes of every `operand` and every predicate of `count.of`;
- the side, since the node reads side-dependent operands;
- the market/range identity of the batch.

Identifiers and declared order SHALL NOT enter the identities of the upstream operand and predicate nodes. Those nodes keep their
existing identities, so they are shared:

- with other setups;
- with `composite_setup` children;
- with other weighted votes.

A batch of specs with weighted votes SHALL end with zero `unforeseen_consumptions`.

#### Scenario: Candidates that differ only in the table

- **WHEN** a batch contains weighted votes that differ only in levels, weights, veto flags or `threshold`
- **THEN** each operand and each predicate of their inputs SHALL be computed once per side.

#### Scenario: Labels change the vote node only

- **WHEN** two weighted votes are identical except for a `voter_id`
- **THEN** their vote nodes SHALL have different identities
- **AND** their operand nodes SHALL have the same identities and be computed once.

#### Scenario: Operand shared with a range setup

- **WHEN** the same ratio operand is the operand of a `range` child in a `composite_setup` and of a weighted vote input
- **THEN** it SHALL be computed once.

### Requirement: No compute regression without a weighted vote

For specs without `weighted_vote_setup` the node set, the node identities, the masks, the evidence and the compute counts SHALL be
identical to those before this change.

#### Scenario: Existing specs

- **WHEN** an existing spec without a weighted vote is evaluated
- **THEN** its results and identities SHALL equal those before this change.
