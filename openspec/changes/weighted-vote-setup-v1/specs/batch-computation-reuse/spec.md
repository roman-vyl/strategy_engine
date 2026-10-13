## ADDED Requirements

### Requirement: Identity of the weighted vote setup

The operands and predicates inside the inputs of a `weighted_vote_setup` SHALL be nodes of the predicate layer with their existing
identities. They SHALL be shared, within an evaluation context:

- with other setups;
- with `composite_setup` children;
- with other weighted votes.

The weighted vote node SHALL add an identity built from the canonical JSON of `threshold` and `voters`. A batch of specs with weighted
votes SHALL end with zero `unforeseen_consumptions`.

#### Scenario: Candidates that differ only in the table

- **WHEN** a batch contains weighted votes that differ only in levels, weights, veto flags or `threshold`
- **THEN** each operand and each predicate of their inputs SHALL be computed once per side.

#### Scenario: Operand shared with a range setup

- **WHEN** the same ratio operand is the operand of a `range` child in a `composite_setup` and of a weighted vote input
- **THEN** it SHALL be computed once.

### Requirement: No compute regression without a weighted vote

For specs without `weighted_vote_setup` the node set, the node identities, the masks, the evidence and the compute counts SHALL be
identical to those before this change.

#### Scenario: Existing specs

- **WHEN** an existing spec without a weighted vote is evaluated
- **THEN** its results and identities SHALL equal those before this change.
