# EMA Pullback Managed Policy v1 Specification

## Purpose

Define the coarse-grained managed-policy replay contract, required opened-trade inputs, strategy-owned outputs, next-bar effectiveness, execution boundary, and determinism.

## Requirements

### Requirement: Coarse-grained replay

The service SHALL evaluate one already-open trade over a requested aligned market range in one application call and SHALL NOT require one HTTP call per bar.

#### Scenario: Replay one open trade

- **WHEN** a caller requests managed replay for an aligned market range
- **THEN** the service SHALL evaluate the entire requested range in one application call.

### Requirement: Required inputs

The request SHALL include the canonical strategy input
(`strategy-evaluation-canonical-input-v1`: `strategy_id`, `raw_spec`),
canonical market range, trade identity, side, entry timestamp, and entry
price. It SHALL NOT include `strategy_version`, caller-supplied
`instance_id`, or `compatibility_profile`.

#### Scenario: Submit managed replay inputs

- **WHEN** managed replay is requested
- **THEN** the request SHALL provide the canonical strategy input and
  market data plus all required opened-trade facts.

#### Scenario: Legacy envelope field is supplied

- **WHEN** a managed-replay request's `strategy` object contains
  `strategy_version`, `instance_id`, or `compatibility_profile`
- **THEN** strict HTTP validation SHALL reject the request before
  replay begins.

### Requirement: Strategy-owned outputs

The response SHALL expose ordered phase-change, active-stop, active-take, and runtime-exit events; per-bar active policy state; and final managed state.

#### Scenario: Return a managed policy replay

- **WHEN** managed replay succeeds
- **THEN** ordered policy events, per-bar decisions, and the final managed state SHALL be returned.

### Requirement: Next-bar effectiveness

Stop, take, and runtime-exit policy changes calculated at the end of bar N SHALL identify bar N+1 as their effective boundary.

#### Scenario: Emit a policy change at bar N

- **WHEN** a stop, take, or runtime-exit decision is produced at the end of bar N
- **THEN** its effective boundary SHALL be identified as bar N+1.

### Requirement: Execution exclusion

The service SHALL NOT decide actual OHLC stop hits, fill price, fees, PnL, or exchange order status.

#### Scenario: Return managed policy without execution facts

- **WHEN** replay produces stop, take, or close decisions
- **THEN** it SHALL return policy intent only
- **AND** SHALL NOT fabricate execution or accounting facts.

### Requirement: Determinism

The same spec, market range, and trade facts SHALL produce identical events and final state.

#### Scenario: Repeat an identical managed replay

- **WHEN** identical strategy, market, and opened-trade inputs are replayed
- **THEN** the ordered events and final state SHALL be identical.

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
