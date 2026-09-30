## ADDED Requirements

### Requirement: Predicate feature references use the canonical plan

Feature references inside `composite_setup` children SHALL be planned
as ordinary `PlannedFeature` entries of the strategy's single
`IndicatorPlan`:

- they SHALL use the same kind-specific labels and the same
  deduplication as every other planned feature;
- semantic setup children SHALL be planned by their existing
  per-component planning under the internal key
  `"{instance_id}/{child_id}"`.

For a spec without `composite_setup`, the plan (features, order and
`plan_hash`) SHALL be unchanged.

#### Scenario: Shared feature

- **WHEN** a predicate requests `adx` on `1h` with period 14
- **AND** a `trend_strength_episode_blocker` requests the same ADX
- **THEN** the plan SHALL contain one `adx` feature for (`1h`, 14).

#### Scenario: Plan unchanged without composite

- **WHEN** a spec contains no `composite_setup`
- **THEN** its `plan_hash` SHALL equal the `plan_hash` produced before
  this change.

### Requirement: Label collisions fail closed

If the identity of a predicate feature reference differs from the
identity of the planned feature already stored under the same label,
planning SHALL fail with `InvalidRequestError`. The predicate SHALL NOT
read a series other than the one it requested.

#### Scenario: EMA source collision

- **WHEN** the anchor stack plans `ema` on `1h`, period 100, source
  `close`
- **AND** a predicate requests `ema` on `1h`, period 100, source `open`
- **THEN** planning SHALL fail with `InvalidRequestError`.

### Requirement: Timeframe support

A predicate feature reference SHALL accept any timeframe that the
indicator evaluator accepts: `base` or an integral multiple of the base
timeframe. Any other timeframe SHALL fail at the same point, and with
the same error, as for any other planned feature.

#### Scenario: Mixed timeframes in one composite

- **WHEN** one composite references features on `5m`, `15m`, `1h` and
  `4h` with a `5m` base
- **THEN** all four SHALL be planned in the one plan
- **AND** SHALL be evaluated through the existing completed-bar
  alignment.
