# EMA Pullback Authoring Config Validation v1

## ADDED Requirements

### Requirement: Authoritative instance validation

Strategy Engine SHALL own validation of `ema_pullback` instance semantics.

#### Scenario: Validate an EMA Pullback authoring instance

- **WHEN** an authoring consumer submits an `ema_pullback` instance for validation
- **THEN** Strategy Engine SHALL determine whether its strategy semantics are valid.

### Requirement: Existing Workbench authoring shape

The validation endpoint SHALL accept the existing Workbench authoring shape.

#### Scenario: Submit a Workbench authoring payload

- **WHEN** a caller submits the existing Workbench `{instances: [...]}` payload
- **THEN** the endpoint SHALL accept and process each authoring instance.

### Requirement: Canonical semantic validation

Validation SHALL translate authoring instances to the canonical strategy envelope and reuse the canonical strategy validator.

#### Scenario: Translate and validate an authoring instance

- **WHEN** an authoring instance is processed
- **THEN** it SHALL be translated to a canonical `StrategySpecEnvelope`
- **AND** the translated envelope SHALL be checked by the canonical strategy validator.

### Requirement: Stable invalid-instance path

Invalid instances SHALL return `valid=false` with an `instances[N]` path.

#### Scenario: One submitted instance is invalid

- **WHEN** the instance at index `N` fails translation or semantic validation
- **THEN** the response SHALL set `valid` to `false`
- **AND** SHALL report the error path as `instances[N]`.
