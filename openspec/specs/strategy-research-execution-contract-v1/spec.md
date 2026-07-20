# Strategy Research Execution Contract v1 Specification

## Purpose

Define the versioned per-bar decision contract consumed by Research Service and the boundary that keeps execution and accounting facts outside Strategy Engine.

## Requirements

### Requirement: Versioned per-bar decision contract

Strategy Engine SHALL expose a versioned per-bar decision contract sufficient for a separate Research Service to execute fills without importing strategy internals. The range contract SHALL include strategy and market identity, aligned range, bar count, market-data hash, per-bar decision series, and evidence. Managed replay SHALL expose explicit next-bar effective timing.

#### Scenario: Consume Engine decisions in Research Service

- **WHEN** Research Service receives a range evaluation or managed replay
- **THEN** it SHALL receive a versioned contract with the identity, alignment, provenance, and per-bar policy data required for external execution
- **AND** managed decisions SHALL state when they become effective.

### Requirement: Execution facts remain external

Strategy Engine SHALL NOT return executed fills, completed trades, fees, or PnL.

#### Scenario: Inspect an Engine decision response

- **WHEN** Strategy Engine returns entry, exit, stop, take, or managed policy decisions
- **THEN** the response SHALL contain no fabricated fill, completed-trade, fee, or PnL facts.
