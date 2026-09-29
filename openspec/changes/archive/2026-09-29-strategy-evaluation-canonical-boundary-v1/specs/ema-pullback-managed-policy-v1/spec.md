## MODIFIED Requirements

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
