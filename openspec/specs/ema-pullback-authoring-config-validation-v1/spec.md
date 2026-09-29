# EMA Pullback Authoring Config Validation v1

## Purpose

Define Strategy Engine's authoritative validation contract for EMA Pullback authoring instances submitted by Workbench-compatible consumers.

## Requirements

### Requirement: Authoritative instance validation

Strategy Engine SHALL own validation of `ema_pullback` instance semantics.

#### Scenario: Validate an EMA Pullback authoring instance

- **WHEN** an authoring consumer submits an `ema_pullback` instance for validation
- **THEN** Strategy Engine SHALL determine whether its strategy semantics are valid.

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

### Requirement: Path/body strategy_id invariant

Every instance's `strategy_id` SHALL equal the path `strategy_id`. This
is a boundary invariant enforced by the authoring-validation endpoint
itself, before any instance reaches semantic (`raw_spec`) validation —
it SHALL NOT be discovered indirectly through a downstream unknown-
strategy error, and it SHALL NOT depend on the strategy registry
currently containing only one strategy.

#### Scenario: All instances match the path strategy_id

- **WHEN** every instance's `strategy_id` equals the path `strategy_id`
- **THEN** the endpoint SHALL proceed to semantic validation for each
  instance.

#### Scenario: An instance's strategy_id does not match the path

- **WHEN** any instance's `strategy_id` differs from the path
  `strategy_id`
- **THEN** the endpoint SHALL reject the whole request before semantic
  validation of any instance
- **AND** the rejection SHALL identify the offending instance by
  `instances[N].strategy_id`.

#### Scenario: Mismatch among multiple instances

- **WHEN** a batch of instances contains a mismatch at index `N`, with
  matching instances at other indices
- **THEN** the endpoint SHALL reject the whole request, identifying
  index `N`
- **AND** SHALL NOT return a partially successful result mixing
  strategy types within one path-scoped authoring-validation call.

### Requirement: Canonical semantic validation

Validation SHALL build a canonical strategy input (`strategy_id`,
`raw_spec`) directly from each instance and reuse the existing canonical
strategy validator. It SHALL NOT translate instances into a legacy
envelope shape. The canonical
strategy validator SHALL determine whether the instance's `raw_spec`
contains a deterministic, market-data-independent config-semantic
error that the production evaluator would otherwise only discover once
evaluation runs against a loaded `FeatureFrame`. Specifically, the
canonical strategy validator SHALL reject a `raw_spec` where:

- any component (blocker, trigger, risk filter, setup, or exit rule)
  specifies a `component_id` the evaluator does not recognize for that
  component family;
- any exit rule, setup, or blocker — the three component kinds
  pre-decomposition BBB required explicit rule/component identity for
  — omits `instance_id` or supplies an empty one;
- two or more exit rules, two or more setups, or two or more blockers
  share the same `instance_id` within that component kind's identity
  domain: for setups, uniqueness spans every setup in `raw_spec.setups`;
  for blockers, uniqueness spans every blocker in
  `raw_spec.components.blockers`; for exit rules, uniqueness spans
  every exit rule across `trade_management.exit_policy.always_on` and
  all three profiles (`aligned`, `countertrend`, `neutral`) combined —
  not per-group;
- the static structure the evaluator requires to even begin dispatch
  (for example `trade_sides`, or a component entry that is not an
  object) is malformed.

These identity requirements (mandatory non-empty `instance_id`, and
uniqueness within the domain above) restore the invariant
pre-decomposition BBB enforced at strategy-spec construction time for
setups, blockers, and exit rules alike; they are not new semantics
introduced by Strategy Engine.

The canonical strategy validator SHALL NOT attempt to determine
whether market data is available, whether any runtime or position
state exists, whether an external service is reachable, or what the
strategy's evaluated numeric output would be — those remain
execution-time concerns outside this validator's scope.

#### Scenario: Validate a canonical instance

- **WHEN** a canonical deployable instance is processed
- **THEN** its `strategy_id` and `raw_spec` SHALL be checked by the
  canonical strategy validator with no intermediate legacy-envelope
  translation step.

#### Scenario: Unsupported component_id is rejected

- **WHEN** an authoring instance's `raw_spec` configures a blocker,
  trigger, risk filter, setup, or exit rule with a `component_id` the
  evaluator does not recognize for that component family
- **THEN** the endpoint SHALL report `valid=false` for that instance
- **AND** this SHALL be detected without loading market data or a
  `FeatureFrame`.

#### Scenario: Missing rule/component identity is rejected

- **WHEN** an authoring instance's `raw_spec` configures an exit rule,
  a setup, or a blocker that omits `instance_id` or supplies an empty
  one
- **THEN** the endpoint SHALL report `valid=false` for that instance.

#### Scenario: Duplicate instance_id within a domain is rejected

- **WHEN** an authoring instance's `raw_spec` configures two setups
  sharing one `instance_id`, or two blockers sharing one `instance_id`,
  or two exit rules sharing one `instance_id` (whether in the same
  exit group or across `always_on`/`aligned`/`countertrend`/`neutral`)
- **THEN** the endpoint SHALL report `valid=false` for that instance.

#### Scenario: A statically well-formed instance validates

- **WHEN** an authoring instance's `raw_spec` uses only recognized
  `component_id`s for every configured component family, supplies a
  non-empty and domain-unique `instance_id` wherever required (setups,
  blockers, exit rules), and is otherwise well-formed
- **THEN** the endpoint SHALL report `valid=true` for that instance,
  regardless of whether market data for that instrument/timeframe is
  currently available anywhere in the system.

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
