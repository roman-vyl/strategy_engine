## ADDED Requirements

### Requirement: Anchor stack width band setup features

`anchor_stack_width_band_setup` SHALL be planned with the anchor-stack
`fast` and `slow` features and one ATR feature for (`atr_timeframe`,
`atr_period`), added through the same ATR planning and deduplication
as every other ATR consumer. It SHALL NOT introduce a new indicator
kind. A composite child SHALL be planned under the internal key
`"{instance_id}/{child_id}"`.

For a spec without `anchor_stack_width_band_setup`, the plan
(features, order and `plan_hash`) SHALL be unchanged.

#### Scenario: Shared ATR

- **WHEN** a spec declares `anchor_stack_width_setup` and
  `anchor_stack_width_band_setup` with the same `atr_timeframe` and
  `atr_period`
- **THEN** the plan SHALL contain one ATR feature for that pair.

#### Scenario: Plan unchanged without the band setup

- **WHEN** a spec contains no `anchor_stack_width_band_setup`
- **THEN** its `plan_hash` SHALL equal the `plan_hash` produced before
  this change.
