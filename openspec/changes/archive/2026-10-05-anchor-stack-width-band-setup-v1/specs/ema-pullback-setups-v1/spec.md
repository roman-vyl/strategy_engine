## MODIFIED Requirements

### Requirement: Supported setup determinism

The engine SHALL implement `untouched_anchor_setup`, `ema_bounce_counter_setup`, `anchor_stack_width_setup` and `anchor_stack_width_band_setup` with deterministic, bar-aligned outputs for identical market bars, features, parameters, and side.

#### Scenario: Evaluate a supported setup

- **WHEN** any supported setup receives identical inputs
- **THEN** its bar-aligned mask and trace SHALL be deterministic for those inputs.

### Requirement: Composite setup is a supported setup

The engine SHALL support `composite_setup` in addition to
`untouched_anchor_setup`, `ema_bounce_counter_setup`,
`anchor_stack_width_setup` and `anchor_stack_width_band_setup`, as
specified by `ema-pullback-composite-setup-v1`. `composite_setup` SHALL
participate in context consumption order, setup composition, evidence
and determinism exactly like the other supported setups.

#### Scenario: Gate a composite setup with context

- **WHEN** a `composite_setup` declares `context_consumption`
- **THEN** its composite local mask SHALL be calculated before the
  context gate
- **AND** the gate SHALL only filter the resulting local mask.

#### Scenario: Existing setups are unaffected

- **WHEN** a spec declares no `composite_setup`
- **THEN** setup masks, traces and `pre_trigger_allowed` SHALL be
  bit-identical to the evaluation before this change.

## ADDED Requirements

### Requirement: Anchor stack width band setup

`anchor_stack_width_band_setup` SHALL admit a base bar iff the current
width of the anchor stack lies in an inclusive band:

- `width_atr = |fast − slow| / atr`, where `fast` and `slow` are the
  anchor-stack EMA columns and `atr` is the ATR column of
  (`atr_timeframe`, `atr_period`);
- the bar SHALL be admitted iff `min_width_atr ≤ width_atr` and, when
  `max_width_atr` is present, `width_atr ≤ max_width_atr`.

Parameters:

- `min_width_atr` SHALL be present and SHALL be a finite number
  greater than zero;
- `max_width_atr` MAY be present; when present it SHALL be a finite
  number not less than `min_width_atr`; when absent the band SHALL
  have no upper bound; `null` SHALL be rejected;
- `atr_timeframe` SHALL default to `base` and `atr_period` to `14`,
  with the same meaning as in `anchor_stack_width_setup`;
- booleans SHALL NOT be accepted as numbers, and any other key SHALL
  be rejected.

Invalid parameters SHALL be rejected by static validation, without
market data, for a top-level setup and for a `composite_setup` child.

The component SHALL read the current bar only. It SHALL NOT use a
lookback, a trailing extreme, a hold window or any state carried
across bars, and SHALL NOT read the anchor column.

The bar SHALL NOT be admitted where `fast`, `slow` or `atr` is missing
or non-finite, or `atr ≤ 0`.

The component SHALL be side-free: the same mask SHALL be produced for
both sides.

The trace SHALL contain, per bar, `blocked_reason` (one of
`indicator_not_ready`, `width_below_min`, `width_above_max`, or empty
when admitted), `width_atr`, `min_width_atr`, `max_width_atr` (`null`
when absent), `fast_ema`, `slow_ema` and `atr_value`.

`anchor_stack_width_setup` SHALL be unchanged by this component: its
parameters, defaults, trace and identity SHALL remain as before.

#### Scenario: Inclusive bounds

- **WHEN** `min_width_atr` is 5 and `max_width_atr` is 15
- **THEN** a bar with `width_atr` exactly 5 SHALL be admitted
- **AND** a bar with `width_atr` exactly 15 SHALL be admitted
- **AND** a bar with `width_atr` above 15 SHALL be blocked with
  `width_above_max`.

#### Scenario: No upper bound

- **WHEN** `min_width_atr` is 5 and `max_width_atr` is absent
- **THEN** every ready bar with `width_atr ≥ 5` SHALL be admitted.

#### Scenario: Inverted band is rejected

- **WHEN** `max_width_atr` is less than `min_width_atr`
- **THEN** static validation SHALL reject the spec.

#### Scenario: Missing lower bound is rejected

- **WHEN** `min_width_atr` is absent
- **THEN** static validation SHALL reject the spec.

#### Scenario: Indicator not ready

- **WHEN** `atr` is not finite on a bar
- **THEN** the bar SHALL NOT be admitted
- **AND** its `blocked_reason` SHALL be `indicator_not_ready`.

#### Scenario: Same width as the existing width setup

- **WHEN** `anchor_stack_width_band_setup` and `anchor_stack_width_setup`
  use the same ATR
- **THEN** on every bar where both are ready, `width_atr` of the band
  setup SHALL equal `current_width_atr` of the existing setup.
