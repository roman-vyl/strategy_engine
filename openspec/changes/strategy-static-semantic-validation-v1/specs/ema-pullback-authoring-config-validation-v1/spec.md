## MODIFIED Requirements

### Requirement: Canonical semantic validation

Validation SHALL translate authoring instances to the canonical strategy
envelope and reuse the canonical strategy validator. The canonical
strategy validator SHALL determine whether the instance's `raw_spec`
contains a deterministic, market-data-independent config-semantic
error that the production evaluator would otherwise only discover once
evaluation runs against a loaded `FeatureFrame`. Specifically, the
canonical strategy validator SHALL reject a `raw_spec` where:

- any component (blocker, trigger, risk filter, setup, or exit rule)
  specifies a `component_id` the evaluator does not recognize for that
  component family;
- any exit rule or setup that the evaluator keys a per-instance
  mapping by omits `instance_id` or supplies an empty one;
- the static structure the evaluator requires to even begin dispatch
  (for example `trade_sides`, or a component entry that is not an
  object) is malformed.

The canonical strategy validator SHALL NOT attempt to determine
whether market data is available, whether any runtime or position
state exists, whether an external service is reachable, or what the
strategy's evaluated numeric output would be — those remain
execution-time concerns outside this validator's scope.

#### Scenario: Translate and validate an authoring instance

- **WHEN** an authoring instance is processed
- **THEN** it SHALL be translated to a canonical `StrategySpecEnvelope`
- **AND** the translated envelope SHALL be checked by the canonical
  strategy validator.

#### Scenario: Unsupported component_id is rejected

- **WHEN** an authoring instance's `raw_spec` configures a blocker,
  trigger, risk filter, setup, or exit rule with a `component_id` the
  evaluator does not recognize for that component family
- **THEN** the endpoint SHALL report `valid=false` for that instance
- **AND** this SHALL be detected without loading market data or a
  `FeatureFrame`.

#### Scenario: Missing rule/component identity is rejected

- **WHEN** an authoring instance's `raw_spec` configures an exit rule
  or a setup that omits `instance_id` or supplies an empty one
- **THEN** the endpoint SHALL report `valid=false` for that instance.

#### Scenario: A statically well-formed instance validates

- **WHEN** an authoring instance's `raw_spec` uses only recognized
  `component_id`s for every configured component family, supplies
  `instance_id` wherever the evaluator requires rule/component
  identity, and is otherwise well-formed
- **THEN** the endpoint SHALL report `valid=true` for that instance,
  regardless of whether market data for that instrument/timeframe is
  currently available anywhere in the system.
