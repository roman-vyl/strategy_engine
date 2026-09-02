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
