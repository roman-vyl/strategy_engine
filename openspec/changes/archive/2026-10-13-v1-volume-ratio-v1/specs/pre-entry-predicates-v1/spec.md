## ADDED Requirements

### Requirement: Leg mean operand shape

A leg mean reference SHALL be `{"leg_mean": {"episode", "leg", "field"}}`; all three are required and no other field is allowed.
`episode` SHALL name an episode declared in `raw_spec.ema_stack_episode`, `leg` SHALL be `impulse` or `pullback` and `field` SHALL be
`volume`. It SHALL be accepted as a side of a `ratio`, as the operand of a `range` and of a `compare`, and rejected as the operand
of a `change`.

#### Scenario: Malformed leg mean

- **WHEN** a leg mean names an undeclared episode, an unknown `leg` or `field`, lacks a required field or has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg mean value

On each bar `t` the impulse leg SHALL be the base bars from `origin_bar` to `peak_bar` of the current touch and the pullback leg the
base bars from `peak_bar + 1` to `t`, both ends inclusive. The value SHALL be the arithmetic mean of the field over the leg's bars
and SHALL be missing when the current touch has no valid wave, when the leg is empty or when any bar of the leg has a non-finite
field. Bars after `t` SHALL NOT be read.

#### Scenario: Pullback starts after the peak

- **WHEN** `t` is the peak bar
- **THEN** the pullback mean SHALL be missing.

#### Scenario: Legs

- **WHEN** a wave has origin 10, peak 14 and `t` = 20
- **THEN** the impulse mean SHALL average bars 10 to 14 and the pullback mean bars 15 to 20.

### Requirement: Volume ratio filter

`range(ratio(leg_mean(pullback, volume), leg_mean(impulse, volume)))` with `bounds` `exclusive` and `empty: pass` SHALL block an
entry when the ratio is not greater than `min` or not less than `max` (both inclusive), each bound optional. A zero or missing impulse mean SHALL make
the ratio missing, and a missing ratio SHALL pass.

#### Scenario: Zero impulse volume

- **WHEN** the impulse leg has mean volume 0
- **THEN** the entry SHALL pass.

#### Scenario: Threshold

- **WHEN** the ratio equals `min` or equals `max`
- **THEN** the entry SHALL be blocked.
