## ADDED Requirements

### Requirement: Identity of the EMA stack episode

An episode declared in `raw_spec.ema_stack_episode` SHALL be resolved per side into one node of kind `episode.ema_stack`. Its identity SHALL carry `window_bars`, `break_bars`, `history_bars` and the side, and its upstream SHALL be the fast, anchor and slow EMA feature nodes. The `episode_ref` label SHALL NOT enter the identity. An episode operand SHALL carry its `entity`, `index` and `field`, with the episode node as upstream.

#### Scenario: Candidates sharing one episode

- **WHEN** a batch contains candidates that declare the same episode parameters and stack but differ elsewhere
- **THEN** the episode node SHALL be computed once per side per batch
- **AND** memoized and non-memoized evaluation SHALL produce bit-identical outputs
- **AND** the memoized evaluation SHALL end with zero `unforeseen_consumptions`.

### Requirement: No compute regression without an EMA stack episode

For specs without `ema_stack_episode`, evaluation outputs, memoized compute counts per node family, node identities and `plan_hash` SHALL be identical to the evaluation before this change.

#### Scenario: Existing specs

- **WHEN** the existing memo compute-count, identity and plan-hash tests run after this change
- **THEN** outputs, compute counts, identities and plan hashes SHALL match their pre-change values exactly.
