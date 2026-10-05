## MODIFIED Requirements

### Requirement: Children

`params.children` SHALL be a non-empty list. Each child SHALL have:

- a `child_id` unique within the composite and not containing `/`;
- exactly one of `predicate` or `setup`.

For a `setup` child:

- its `component_id` SHALL be one of `untouched_anchor_setup`,
  `ema_bounce_counter_setup`, `anchor_stack_width_setup`,
  `anchor_stack_width_band_setup`;
- it SHALL NOT carry `instance_id` or `context_consumption`.

`composite_setup` SHALL NOT be a child.

#### Scenario: Nested gate is rejected

- **WHEN** a setup child declares `context_consumption`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Nested composite is rejected

- **WHEN** a setup child has `component_id` `composite_setup`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Width band child equals the width band setup

- **WHEN** a composite has a single path requiring a single
  `anchor_stack_width_band_setup` child
- **THEN** the composite local mask SHALL equal the local mask of the
  same `anchor_stack_width_band_setup` declared directly.
