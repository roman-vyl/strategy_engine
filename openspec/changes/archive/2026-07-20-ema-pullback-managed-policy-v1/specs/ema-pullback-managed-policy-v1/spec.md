# EMA Pullback Managed Policy v1 Specification

## ADDED Requirements

### Requirement: Coarse-grained replay

The service SHALL evaluate one already-open trade over a requested aligned market range in one application call and SHALL NOT require one HTTP call per bar.

#### Scenario: Replay one open trade

- **WHEN** a caller requests managed replay for an aligned market range
- **THEN** the service SHALL evaluate the entire requested range in one application call.

### Requirement: Required inputs

The request SHALL include canonical strategy spec, canonical market range, trade identity, side, entry timestamp, and entry price.

#### Scenario: Submit managed replay inputs

- **WHEN** managed replay is requested
- **THEN** the request SHALL provide the canonical strategy and market data plus all required opened-trade facts.

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
