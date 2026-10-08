## ADDED Requirements

### Requirement: Identity of the trend episode structure

A `trend_episode` structure SHALL be resolved per side into one node of kind `structure.trend_episode`. Its identity SHALL carry `window_bars`, `break_bars`, `history_bars` and the side, and its upstream SHALL be the fast, anchor and slow EMA feature nodes. The `structure_ref` label SHALL NOT enter the identity. A structure-form `state` predicate node SHALL carry its field and its operator and value or set, with the structure node as upstream.

#### Scenario: Candidates sharing one structure

- **WHEN** a batch contains candidates that declare the same structure parameters and stack but differ elsewhere
- **THEN** the structure node SHALL be computed once per side per batch
- **AND** memoized and non-memoized evaluation SHALL produce bit-identical outputs
- **AND** the memoized evaluation SHALL end with zero `unforeseen_consumptions`.

### Requirement: No compute regression without market structure

For specs without `market_structure`, evaluation outputs, memoized compute counts per node family, node identities and `plan_hash` SHALL be identical to the evaluation before this change.

#### Scenario: Existing specs

- **WHEN** the existing memo compute-count, identity and plan-hash tests run after this change
- **THEN** outputs, compute counts, identities and plan hashes SHALL match their pre-change values exactly.
