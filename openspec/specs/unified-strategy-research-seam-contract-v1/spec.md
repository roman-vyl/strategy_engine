# Unified Strategy Research Seam Contract v1 Specification

## Purpose

Define the shared service seam between Strategy Engine and Research Service, including complementary managed ownership and the production legacy-runtime boundary.

## Requirements

### Requirement: Single physical seam

Strategy Engine and Research Service SHALL describe the same cut through the same legacy callers and callees.

#### Scenario: Map a legacy mixed responsibility

- **WHEN** a legacy strategy/research call path is assigned to the new services
- **THEN** both sides SHALL use the same normative seam matrix and complementary ownership.

### Requirement: Managed ownership

Strategy Engine SHALL return policy decisions only. Research Service SHALL own arbitration, fills, PnL, and trade records.

#### Scenario: Consume a managed policy decision

- **WHEN** Strategy Engine returns stop, take, phase, or runtime-exit policy
- **THEN** it SHALL NOT claim execution facts
- **AND** Research Service SHALL own hit arbitration, fills, accounting, and trade records.

### Requirement: No legacy runtime

Neither service SHALL import or execute `legacy_source` in production.

#### Scenario: Inspect production dependencies

- **WHEN** production code is checked for legacy coupling
- **THEN** it SHALL contain no import, execution, or fallback path to `legacy_source`.
