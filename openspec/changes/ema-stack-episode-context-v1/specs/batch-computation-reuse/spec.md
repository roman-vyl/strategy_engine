## ADDED Requirements

### Requirement: Identity of the EMA stack episode context

An `ema_stack_episode` context SHALL be resolved per side into one node with kind `context.ema_stack_episode`, whose identity carries `window_bars`, `break_bars`, `history_bars` and the side, and whose upstream is the fast, anchor and slow EMA feature nodes. The `context_ref` label SHALL NOT enter the identity. Predicate nodes that read an episode field SHALL carry the field, the wave selector and the episode node as upstream.

#### Scenario: Candidates sharing one episode

- **WHEN** a batch contains candidates that declare the same episode parameters and stack but differ elsewhere
- **THEN** the episode node SHALL be computed once per side per batch
- **AND** memoized and non-memoized evaluation SHALL produce bit-identical outputs
- **AND** the memoized evaluation SHALL end with zero `unforeseen_consumptions`.

### Requirement: No compute regression without the EMA stack episode context

For specs without an `ema_stack_episode` context, evaluation outputs, memoized compute counts per node family, node identities and `plan_hash` SHALL be identical to the evaluation before this change.

#### Scenario: Existing specs

- **WHEN** the existing memo compute-count, identity and plan-hash tests run after this change
- **THEN** outputs, compute counts, identities and plan hashes SHALL match their pre-change values exactly.
