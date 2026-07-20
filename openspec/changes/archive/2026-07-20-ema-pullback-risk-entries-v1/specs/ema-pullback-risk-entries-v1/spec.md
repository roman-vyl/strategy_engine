# EMA Pullback Risk and Final Entries v1 Specification

## ADDED Requirements

### Requirement: BBB-compatible risk resolution

The engine SHALL accept `components.risk` as either a component-id string or an object containing `component_id`. Version 1 SHALL support `no_risk_filter` and SHALL reject unknown risk components.

#### Scenario: Resolve the configured risk component

- **WHEN** risk is supplied as a string or component object
- **THEN** `no_risk_filter` SHALL be evaluated with BBB-compatible semantics
- **AND** any unsupported component SHALL be rejected.

### Requirement: Final entry composition

For each enabled side, the final entry mask SHALL be the element-wise conjunction of the existing pre-risk entry mask and the risk allow mask. For `no_risk_filter`, this SHALL preserve the pre-risk mask exactly.

#### Scenario: Compose a final entry mask

- **WHEN** risk evaluation completes for an enabled side
- **THEN** `entry_allowed` SHALL equal `pre_risk_entry_allowed` AND `risk_allowed`
- **AND** `no_risk_filter` SHALL preserve the pre-risk mask exactly.

### Requirement: Honest readiness

A successful range evaluation SHALL expose final long and short entry masks and mark `entries_ready=true`. Its overall stage and decision readiness SHALL match all semantic layers currently wired into the production evaluator.

#### Scenario: Return final entry masks

- **WHEN** a strategy range evaluation succeeds
- **THEN** it SHALL expose final entry masks and `entries_ready=true`
- **AND** the overall readiness metadata SHALL accurately describe the accumulated production stage.
