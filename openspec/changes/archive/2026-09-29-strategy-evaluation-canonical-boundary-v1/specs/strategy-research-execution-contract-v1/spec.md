## MODIFIED Requirements

### Requirement: Versioned per-bar decision contract

Strategy Engine SHALL expose a versioned per-bar decision contract
sufficient for a separate Research Service to execute fills without
importing strategy internals. The range contract SHALL include strategy
identity, market identity, aligned range, bar count, market-data hash,
per-bar decision series, and evidence. Strategy identity here means
`strategy_id` and the provenance `config_hash`
(`strategy-evaluation-canonical-input-v1`) only — it does NOT include
`strategy_version` or a caller-supplied `instance_id`; retiring those
two fields does not narrow this requirement's "strategy identity"
clause below its post-cutover meaning. Managed replay SHALL expose
explicit next-bar effective timing.

#### Scenario: Consume Engine decisions in Research Service

- **WHEN** Research Service receives a range evaluation or managed
  replay
- **THEN** it SHALL receive a versioned contract with the identity,
  alignment, provenance, and per-bar policy data required for external
  execution
- **AND** managed decisions SHALL state when they become effective.

#### Scenario: Strategy identity after canonicalization

- **WHEN** a range evaluation response is inspected after this change
- **THEN** its strategy identity fields are exactly `strategy_id` and
  `config_hash`
- **AND** the absence of `strategy_version`/`instance_id` is not a
  contract violation.
