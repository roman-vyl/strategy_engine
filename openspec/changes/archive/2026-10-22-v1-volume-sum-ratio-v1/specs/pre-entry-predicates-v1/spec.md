## ADDED Requirements

### Requirement: Leg sum operand shape

A leg sum reference SHALL be `{"leg_sum": {"episode", "leg", "field"}}`; all three are required and no other field is allowed.
`episode` SHALL name an episode declared in `raw_spec.ema_stack_episode`, `leg` SHALL be `impulse` or `pullback` and `field` SHALL be
`volume`. It SHALL be accepted as a side of a `ratio`, as the operand of a `range`, of a `compare` and of a weighted vote input, and
rejected as the operand of a `change`.

#### Scenario: Malformed leg sum

- **WHEN** a leg sum names an undeclared episode, an unknown `leg` or `field`, lacks a required field or has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg sum value

On each bar `t` the legs SHALL be those of the leg mean operand: the impulse from `origin_bar` to `peak_bar` of the current touch
and the pullback from `peak_bar + 1` to `t`, both ends inclusive. The value SHALL be the sum of the field over the leg's bars and
SHALL be missing when the touch has no valid wave, when the leg is empty or when any bar of the leg has a non-finite field. Bars
after `t` SHALL NOT be read.

#### Scenario: Legs

- **WHEN** a wave has origin 10, peak 14 and `t` = 20
- **THEN** the impulse sum SHALL add bars 10 to 14 and the pullback sum bars 15 to 20.

#### Scenario: Peak bar

- **WHEN** `t` is the peak bar
- **THEN** the pullback sum SHALL be missing.

### Requirement: Volume sum ratio

`ratio(leg_sum(pullback, volume), leg_sum(impulse, volume))` SHALL be the pullback volume sum divided by the impulse volume sum. It
SHALL be missing when either sum is missing or the impulse sum is not greater than the ratio's `right_floor` (default 0). It SHALL
be the same on the long and the short side.

#### Scenario: Zero impulse volume

- **WHEN** the impulse leg has volume sum 0
- **THEN** the ratio SHALL be missing and a `range` with `empty: pass` SHALL not block the bar.

#### Scenario: Value

- **WHEN** the impulse sums to 2000 and the pullback to 100
- **THEN** the ratio SHALL be 0.05.
