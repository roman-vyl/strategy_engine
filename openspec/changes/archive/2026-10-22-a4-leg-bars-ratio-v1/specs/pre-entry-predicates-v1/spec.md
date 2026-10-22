## ADDED Requirements

### Requirement: Leg bars operand shape

A leg bars reference SHALL be `{"leg_bars": {"episode", "leg"}}`; both are required and no other field is allowed. `episode` SHALL
name a declared episode and `leg` SHALL be `impulse` or `pullback`. It SHALL be accepted where a leg sum is accepted and rejected as
the operand of a `change`.

#### Scenario: Malformed leg bars

- **WHEN** `leg` is missing or neither `impulse` nor `pullback`, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg bars value

On a bar `t` with a valid wave of the current touch, the impulse value SHALL be `P − S* + 1` and the pullback value `t − P + 1`. It
SHALL be missing when the touch has no valid wave. Bars after `t` SHALL NOT be read.

#### Scenario: Pullback ten times longer

- **WHEN** the impulse spans bars 100..109 and the evaluated bar is 199
- **THEN** the impulse value SHALL be 10, the pullback value 100 and `ratio(pullback, impulse)` 10.
