## REMOVED Requirements

### Requirement: Existing Workbench authoring shape

**Reason**: Research Service's config layer no longer produces the
legacy nested Workbench authoring shape (`instance_id`, `market{}`,
`strategy.anchor_stack{}`, ...) — it sends the canonical flat
deployable-instance shape (`canonical-strategy-instance-v1` on the
Research side). Replaced by "Canonical deployable-instance shape"
below.

**Migration**: Callers SHALL send `{instances: [{enabled, strategy_id,
ticker, base_timeframe, raw_spec}, ...]}`. No alias or dual-schema
acceptance of the old shape is provided.

## ADDED Requirements

### Requirement: Canonical deployable-instance shape

The validation endpoint SHALL accept a strictly typed canonical flat
deployable strategy-instance shape — not an untyped/opaque object — with
exactly `enabled` (boolean), `strategy_id` (string), `ticker` (string),
`base_timeframe` (string), `raw_spec` (object) per instance, matching
the shape Research Service's config layer already sends. Each field
SHALL be present and well-typed for the instance to be accepted at the
HTTP boundary; `enabled`, `ticker`, and `base_timeframe` SHALL then be
accepted but SHALL NOT affect strategy validation semantics beyond that
boundary check. No instance SHALL be required to carry `instance_id`,
`family`, `variant`, `strategy_version`, or `compatibility_profile`.

#### Scenario: Submit a canonical deployable-instance payload

- **WHEN** a caller submits `{instances: [{enabled, strategy_id, ticker,
  base_timeframe, raw_spec}, ...]}` with every field well-typed
- **THEN** the endpoint SHALL accept and process each instance.

#### Scenario: enabled does not affect validation outcome

- **WHEN** two otherwise-identical instances differ only in `enabled`
- **THEN** both SHALL validate identically.

#### Scenario: Malformed or missing canonical field

- **WHEN** an instance omits `strategy_id`, `ticker`, `base_timeframe`,
  `raw_spec`, or `enabled`, or supplies one with the wrong type (e.g.
  `enabled` as a string, `raw_spec` as a non-object)
- **THEN** strict HTTP validation SHALL reject the request before any
  instance is processed
- **AND** the endpoint SHALL NOT silently ignore, coerce, or drop the
  malformed field.

#### Scenario: Legacy authoring field is supplied

- **WHEN** an instance contains `instance_id`, `family`, `variant`,
  `strategy_version`, `compatibility_profile`, a nested `market` object,
  or a nested `strategy` object
- **THEN** strict HTTP validation SHALL reject the request before any
  instance is processed.

## MODIFIED Requirements

### Requirement: Canonical semantic validation

Validation SHALL build a canonical strategy input (`strategy_id`,
`raw_spec`) directly from each instance and reuse the existing canonical
strategy validator. It SHALL NOT translate instances into a legacy
envelope shape.

#### Scenario: Validate a canonical instance

- **WHEN** a canonical deployable instance is processed
- **THEN** its `strategy_id` and `raw_spec` SHALL be checked by the
  canonical strategy validator with no intermediate legacy-envelope
  translation step.

### Requirement: Stable invalid-instance path

Invalid instances SHALL return `valid=false` with an `instances[N]`
path, identified by index. Successful instance entries SHALL report
`index` and `config_hash`. Neither successful nor failed entries SHALL
report an `instance_id` — none is derived or required at this boundary.

#### Scenario: One submitted instance is invalid

- **WHEN** the instance at index `N` fails validation
- **THEN** the response SHALL set `valid` to `false`
- **AND** SHALL report the error path as `instances[N]`.

#### Scenario: Successful instance entry shape

- **WHEN** an instance validates successfully
- **THEN** its response entry SHALL contain `index` and `config_hash`
- **AND** SHALL NOT contain `instance_id`.
