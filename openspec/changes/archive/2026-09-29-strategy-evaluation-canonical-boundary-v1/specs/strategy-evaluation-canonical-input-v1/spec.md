# Strategy evaluation canonical input v1

## Purpose

Define the single canonical strategy-input shape — `strategy_id` +
`raw_spec` — accepted by every Research-facing strategy evaluation and
validation boundary in Strategy Engine, replacing the legacy
`StrategySpecEnvelope` (`strategy_version`, caller-supplied
`instance_id`, `compatibility_profile`), and the resulting role of
`config_hash` as provenance rather than identity.

## ADDED Requirements

### Requirement: Canonical strategy input

`POST /v1/strategy-evaluations/range`, `POST
/v1/strategy-evaluations/range-batch` (per variant), `POST
/v1/strategy-evaluations/managed-replay`, `POST /strategies/{id}/validate`,
and `POST /strategies/{id}/feature-plan` SHALL accept exactly `strategy_id`
and `raw_spec` as the strategy input. They SHALL NOT accept
`strategy_version`, `instance_id`, `compatibility_profile`, or any nested
nesting different from the existing `strategy` wrapper key already used
on each of these endpoints.

#### Scenario: Valid canonical strategy input accepted

- **WHEN** a request supplies `strategy: {strategy_id, raw_spec}` with no
  other fields
- **THEN** the endpoint accepts it and proceeds to evaluation or
  validation.

#### Scenario: Legacy strategy_version is supplied

- **WHEN** a request's `strategy` object contains `strategy_version`
- **THEN** strict HTTP validation SHALL reject the request before
  evaluation or validation begins.

#### Scenario: Caller-supplied instance_id is supplied

- **WHEN** a request's `strategy` object contains `instance_id`
- **THEN** strict HTTP validation SHALL reject the request before
  evaluation or validation begins
- **AND** Engine SHALL NOT derive, alias, or synthesize an `instance_id`
  on the caller's behalf.

#### Scenario: compatibility_profile is supplied

- **WHEN** a request's `strategy` object contains `compatibility_profile`
- **THEN** strict HTTP validation SHALL reject the request before
  evaluation or validation begins.

### Requirement: No compatibility-profile gate

Strategy evaluation and validation SHALL NOT gate on a
`compatibility_profile` value. Feature-plan construction for
`strategy_id=ema_pullback` SHALL proceed unconditionally from `raw_spec`.

#### Scenario: Feature plan built without a profile selector

- **WHEN** a canonical `ema_pullback` strategy input is validated
- **THEN** the feature plan is built from `raw_spec` alone, with no
  profile-equality check of any kind.

### Requirement: Response echoes no retired field

The `/range` and `/range-batch` per-variant success response SHALL NOT
contain `strategy_version` or `instance_id`. `strategy_id` and
`config_hash` remain present.

#### Scenario: Range response key set

- **WHEN** a range evaluation succeeds
- **THEN** the response contains `strategy_id` and `config_hash`
- **AND** contains no `strategy_version` or `instance_id` key at any
  level.

#### Scenario: Range-batch variant outcome key set

- **WHEN** a range-batch variant succeeds
- **THEN** its embedded result contains `strategy_id` and `config_hash`
- **AND** contains no `strategy_version` or `instance_id` key at any
  level.

### Requirement: config_hash is provenance, not identity

When present in a response, `config_hash` SHALL be computed from
`{strategy_id, raw_spec}` only. It SHALL remain a response/provenance
field and SHALL NOT be treated as, or substituted for, `instance_id`
correlation identity anywhere on this boundary.

#### Scenario: config_hash excludes retired fields

- **WHEN** two requests share the same `strategy_id` and `raw_spec`
- **THEN** their `config_hash` values SHALL be equal regardless of any
  other request content.

### Requirement: Live boundary unaffected

This canonicalization SHALL NOT alter the request or response shape of
`POST /v1/strategy-evaluations/live-entry` or `POST
/v1/strategy-evaluations/open-trade`, and SHALL NOT alter calculation
results produced by the shared calculation core for any endpoint.

#### Scenario: Existing live fixture

- **WHEN** an existing live-entry or open-trade fixture is evaluated
  before and after this change
- **THEN** its request shape, response shape, and calculated result
  SHALL remain unchanged.

#### Scenario: Existing range fixture, calculation-only comparison

- **WHEN** an existing range evaluation fixture's `raw_spec` and market
  inputs are held constant and only the retired envelope fields are
  removed from the request
- **THEN** `entries`, `potential_entries`, `exit_policy`, `contexts`, and
  `component_evidence` in the response SHALL remain unchanged.
