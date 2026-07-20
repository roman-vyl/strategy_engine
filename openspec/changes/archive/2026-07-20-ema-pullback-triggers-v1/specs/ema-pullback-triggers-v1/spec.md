# EMA Pullback Triggers v1 Specification

## ADDED Requirements

### Requirement: Trigger ownership

The independent Strategy Engine SHALL own the semantic implementations of `reclaim_anchor`, `strong_reclaim_anchor`, and `touch_anchor`.

#### Scenario: Evaluate a supported trigger

- **WHEN** an EMA Pullback strategy configures a supported trigger
- **THEN** Strategy Engine SHALL evaluate its semantics internally.

### Requirement: Prior-window reclaim

Reclaim triggers SHALL inspect only the configured number of bars strictly before the evaluated bar. A probe on the current bar SHALL NOT satisfy the prior-probe condition.

#### Scenario: Current bar contains the only reclaim probe

- **WHEN** no qualifying probe exists in the configured strictly-prior window
- **THEN** the reclaim trigger SHALL be false even if the current bar probes the anchor.

### Requirement: Side symmetry

Long and short trigger inequalities SHALL mirror the copied BBB semantics exactly.

#### Scenario: Mirror trigger evaluation by side

- **WHEN** equivalent long and short market configurations are evaluated
- **THEN** their probe, reclaim, touch, and close inequalities SHALL mirror BBB exactly.

### Requirement: Composition

For each enabled side, the engine SHALL calculate `pre_risk_entry_allowed` as the conjunction of upstream `pre_trigger_allowed` and the trigger mask.

#### Scenario: Compose upstream setup and trigger masks

- **WHEN** trigger evaluation completes for an enabled side
- **THEN** `pre_risk_entry_allowed` SHALL equal `pre_trigger_allowed` AND the trigger mask.

### Requirement: Honest capability stage and pipeline boundary

The range API SHALL expose trigger evidence and SHALL report trigger readiness together with the exact accumulated production stage. `pre_risk_entry_allowed` SHALL remain the trigger layer's intermediate artifact for the separate downstream risk and entry layer.

#### Scenario: Return trigger evidence

- **WHEN** a strategy range response includes trigger results
- **THEN** it SHALL expose trigger masks and traces
- **AND** readiness metadata SHALL accurately describe the accumulated production stage.

### Requirement: Golden parity

Acceptance SHALL compare every trigger mask and trace field against the copied BBB implementation for all supported trigger components and both trade sides.

#### Scenario: Run trigger golden parity

- **WHEN** every supported trigger is evaluated for long and short fixtures
- **THEN** each mask and trace field SHALL match the copied BBB implementation.
