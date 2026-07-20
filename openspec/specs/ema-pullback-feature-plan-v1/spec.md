# EMA Pullback Feature Plan v1 Specification

## Purpose

Define Strategy Engine-owned feature planning, canonical BBB compatibility, exact feature discovery, honest capability metadata, and production dependency boundaries for EMA Pullback.

## Requirements

### Requirement: Caller supplies strategy semantics, not indicator plans

The public strategy boundary SHALL accept a strategy envelope. Feature discovery SHALL occur inside Strategy Engine. A BBB caller SHALL NOT need to construct or submit an IndicatorPlan for strategy evaluation.

#### Scenario: Request strategy-owned feature planning

- **WHEN** a caller submits a canonical EMA Pullback strategy envelope
- **THEN** Strategy Engine SHALL discover the required indicator features internally
- **AND** the caller SHALL NOT need to supply an `IndicatorPlan`.

### Requirement: Canonical BBB spec compatibility

Version 1 SHALL accept the canonical JSON shape produced by BBB `strategy_spec_to_dict`. Unsupported or malformed structures SHALL fail with a structured 4xx response and SHALL NOT silently omit requested features.

#### Scenario: Submit a malformed canonical strategy spec

- **WHEN** a canonical EMA Pullback structure is unsupported or malformed
- **THEN** the request SHALL fail with a structured 4xx response
- **AND** requested features SHALL NOT be silently omitted.

### Requirement: Exact feature discovery parity

The planner SHALL preserve BBB feature IDs, insertion order, deduplication, ATR-distance dependencies, and all lookup mappings for anchor stack, contexts, setups, exits, RSI, EMA, and ADX/DMI.

#### Scenario: Build the complete feature matrix

- **WHEN** a strategy spec references features across anchor stack, contexts, setups, exits, RSI, EMA, and ADX/DMI
- **THEN** the resulting plan and lookup mappings SHALL match BBB identifiers, insertion order, deduplication, and dependencies.

### Requirement: Honest capability advertisement

The strategy catalog SHALL advertise `supports_feature_planning=true`. Range-evaluation flags and the evaluation stage SHALL match the semantics currently wired into the production evaluator, and capabilities beyond that advertised stage SHALL NOT report fabricated success.

#### Scenario: Inspect strategy capability metadata

- **WHEN** a caller inspects the EMA Pullback strategy catalog entry
- **THEN** feature planning SHALL be advertised as supported
- **AND** range-evaluation flags and stage SHALL accurately describe the production evaluator.

### Requirement: No legacy production imports

Production code SHALL NOT import from `legacy_source` or BBB packages. Golden tests MAY load copied BBB code only as the parity oracle.

#### Scenario: Enforce the production dependency boundary

- **WHEN** architecture checks inspect production imports
- **THEN** no production module SHALL import `legacy_source` or BBB packages
- **AND** copied BBB code MAY be loaded only by parity tests.
