## ADDED Requirements

### Requirement: Candidate-wide historical projection derives from the same formulas as single-trade replay

Whenever Strategy Engine produces a `HistoricalManagedProjection` for a
candidate, every condition, distance, and rule in that projection SHALL
be derived from the exact same phase-rule, runtime-exit,
stop-management, and take-management formulas that
`/managed-replay`'s single-trade evaluator uses for the same strategy
spec. The projection evaluator SHALL NOT reuse the static exit-policy
evaluator's condition/distance logic, since that evaluator uses
different comparison semantics and does not implement the same
confirm-bars sustain window.

#### Scenario: Formula parity, not reuse of the static evaluator

- **WHEN** a managed strategy spec references a component id that also
  exists in the static exit-policy evaluator (e.g. `rsi_signal_exit`,
  `ema_cross_loss_exit`)
- **THEN** the candidate-wide projection SHALL evaluate that component
  using managed policy's own comparison operators and confirm-bars
  semantics
- **AND** SHALL NOT delegate to the static exit-policy evaluator's
  implementation of the same component id.
