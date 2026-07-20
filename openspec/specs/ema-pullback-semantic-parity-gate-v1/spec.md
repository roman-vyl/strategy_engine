# EMA Pullback Semantic Parity Gate v1 Specification

## Purpose

Define explicit semantic coverage, immutable BBB provenance, reproducible acceptance, machine-readable reporting, honest parity boundaries, and consumer acceptance for EMA Pullback.

## Requirements

### Requirement: Complete explicit semantic coverage

The repository SHALL maintain an explicit manifest covering feature planning, indicators, contexts, context consumption, direction/blockers, setups, triggers, standard exit policy, managed policy, and public API contracts.

#### Scenario: Inspect required semantic coverage

- **WHEN** the parity manifest is validated
- **THEN** every required semantic stage and its tests SHALL be listed explicitly.

### Requirement: Immutable source provenance

The gate SHALL verify every available copied BBB source entry against its recorded SHA-256 before executing parity tests.

#### Scenario: Verify the copied BBB snapshot

- **WHEN** the parity gate starts
- **THEN** every recorded BBB source file SHALL exist and match its SHA-256
- **AND** any missing or changed source SHALL fail the gate.

### Requirement: Reproducible acceptance command

One documented command SHALL execute all required parity tests and return a non-zero status on missing tests, source mismatch, or semantic/API mismatch.

#### Scenario: Run the semantic parity gate

- **WHEN** a consumer runs the documented command
- **THEN** it SHALL execute the explicit parity inventory
- **AND** SHALL fail on any missing test, provenance mismatch, or test failure.

### Requirement: Machine-readable report

The gate SHALL emit a JSON report containing manifest hashes, source verification status, covered stages, pytest result, final pass/fail, and explicit exclusions.

#### Scenario: Read a completed parity report

- **WHEN** the gate finishes
- **THEN** its JSON report SHALL contain provenance, coverage, test, result, and exclusion fields.

### Requirement: Honest parity boundary

The report SHALL NOT claim parity for fill arbitration, same-bar execution order, fees, slippage, trade records, PnL, BBB presentation translation, or live runtime checkpointing.

#### Scenario: Inspect the parity claim boundary

- **WHEN** a parity report is generated
- **THEN** execution, accounting, presentation, and live-runtime exclusions SHALL remain explicit.

### Requirement: Consumer acceptance gate

A new consumer SHALL not accept Strategy Engine semantics unless the semantic parity report is green for the immutable source snapshot used by the port.

#### Scenario: Accept Engine semantics in a new consumer

- **WHEN** a consumer considers the Engine semantic contract accepted
- **THEN** the parity report for the referenced immutable BBB snapshot SHALL be green.
