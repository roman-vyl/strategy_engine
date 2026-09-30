## ADDED Requirements

### Requirement: Composite setup is a supported setup

The engine SHALL support `composite_setup` in addition to
`untouched_anchor_setup`, `ema_bounce_counter_setup` and
`anchor_stack_width_setup`, as specified by
`ema-pullback-composite-setup-v1`. `composite_setup` SHALL participate
in context consumption order, setup composition, evidence and
determinism exactly like the other supported setups.

#### Scenario: Gate a composite setup with context

- **WHEN** a `composite_setup` declares `context_consumption`
- **THEN** its composite local mask SHALL be calculated before the
  context gate
- **AND** the gate SHALL only filter the resulting local mask.

#### Scenario: Existing setups are unaffected

- **WHEN** a spec declares no `composite_setup`
- **THEN** setup masks, traces and `pre_trigger_allowed` SHALL be
  bit-identical to the evaluation before this change.
