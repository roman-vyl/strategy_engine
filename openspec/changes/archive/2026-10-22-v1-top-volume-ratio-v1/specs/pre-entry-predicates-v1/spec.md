## ADDED Requirements

### Requirement: Leg top mean operand shape

A leg top mean reference SHALL be `{"leg_top_mean": {"episode", "leg", "field", "share"}}`; all four are required and no other field
is allowed. `episode` SHALL name a declared episode, `leg` SHALL be `impulse` or `pullback`, `field` SHALL be `volume` and `share` a
finite number greater than 0 and at most 1. It SHALL be accepted where a leg sum is accepted and rejected as the operand of a `change`.

#### Scenario: Malformed leg top mean

- **WHEN** `share` is 0, above 1 or missing, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg top mean value

With the legs of the leg sum operand and `L` the number of bars of the leg, the value SHALL be the mean of the `k` largest field
values of the leg, `k = max(1, ceil(share · L))`, as research computes it in float64. It SHALL be missing when the touch has no valid wave, the leg is
empty or a bar of the leg has a non-finite field. Bars after `t` SHALL NOT be read.

#### Scenario: Top mean

- **WHEN** the pullback has 12 bars, `share` is 0.1 and its two largest volumes are 50 and 30
- **THEN** `k` SHALL be 2 and the value 40.

#### Scenario: Rounding of k

- **WHEN** the leg has 30 bars and `share` is 0.1
- **THEN** `k` SHALL be 3; with 11 bars it SHALL be 2.

### Requirement: Top volume ratio

`ratio(leg_top_mean(pullback), leg_top_mean(impulse))` SHALL be missing when either value is missing or the impulse value is not
greater than the ratio's `right_floor` (default 0).

#### Scenario: Zero impulse volume

- **WHEN** every impulse bar has volume 0
- **THEN** the ratio SHALL be missing.
