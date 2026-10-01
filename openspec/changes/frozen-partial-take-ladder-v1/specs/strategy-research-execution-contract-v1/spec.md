## ADDED Requirements

### Requirement: Optional partial takes on executable entry opportunities

An executable entry opportunity SHALL carry `partial_takes` only when
the partial takes in force for its locked profile (`always_on` plus
that profile) are not empty. When there are none, the key SHALL be
absent and the opportunity SHALL be byte-identical to its form before
this change. The `contract_version` SHALL remain
`"strategy_evaluation_execution.v2"`.

#### Scenario: Opportunity without partial takes

- **WHEN** a spec has no partial take rules
- **THEN** no executable entry opportunity SHALL contain a
  `partial_takes` key
- **AND** the serialized contract SHALL be byte-identical to the
  contract before this change.

#### Scenario: Opportunity with partial takes

- **WHEN** a spec has a partial take in force for an opportunity's
  locked profile
- **THEN** the opportunity SHALL carry `partial_takes` as a top-level
  key next to `initial_take`
- **AND** a consumer that rejects unknown fields SHALL therefore fail
  closed on it rather than silently drop the legs.

### Requirement: Partial take leg shape

Each element of `partial_takes` SHALL be
`{take_id, ratio, fraction_of_initial, attribution}`:

- `take_id` and `attribution.rule_id` SHALL equal the rule's
  `instance_id`;
- `ratio` SHALL be the leg's positive relative distance on the
  opportunity bar, on the same basis as `initial_take.ratio`;
- `fraction_of_initial` SHALL be the configured fraction;
- `attribution.exit_kind` SHALL be `"partial_take"`, a canonical value
  that appears only inside `partial_takes`.

Legs SHALL be ordered by `ratio` ascending, ties by declared order.

#### Scenario: Leg on an opportunity

- **WHEN** a long opportunity is locked to `aligned` and `always_on`
  has `pct_partial_take` `pt_1pct` with `pct` 0.01 and fraction 0.25
- **THEN** its `partial_takes` SHALL be
  `[{"take_id": "pt_1pct", "ratio": 0.01, "fraction_of_initial": 0.25,
  "attribution": {"rule_id": "pt_1pct", "component_id":
  "pct_partial_take", "exit_kind": "partial_take"}}]`.

#### Scenario: Leg of another profile is excluded

- **WHEN** a partial take is configured only in the `countertrend`
  profile
- **AND** an opportunity is locked to `aligned`
- **THEN** that leg SHALL NOT appear on the opportunity.

#### Scenario: Final take attribution is unchanged

- **WHEN** an opportunity has partial takes
- **THEN** `initial_take` SHALL carry the same ratio and attribution
  as it would without the partial take rules.
