## ADDED Requirements

### Requirement: Leg speed operand shape

A leg speed reference SHALL be `{"leg_speed": {"episode", "leg"}}`; both are required and no other field is allowed. `episode` SHALL
name a declared episode and `leg` SHALL be `impulse` or `pullback`. It SHALL be accepted where a leg sum is accepted and rejected as
the operand of a `change`.

#### Scenario: Malformed leg speed

- **WHEN** `leg` is missing or neither `impulse` nor `pullback`, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg speed value

On a bar `t` with a valid wave of the current touch, the impulse value SHALL be `|peak_price − origin_price| / (P − S* + 1)` and the
pullback value `|peak_price − close[t]| / (t − P + 1)`. It SHALL be missing when the touch has no valid wave or an input price is not
finite. Bars after `t` SHALL NOT be read.

#### Scenario: Pullback three times faster

- **WHEN** the impulse rises 10 over the bars `S*..P` (10 bars) and the close of `t` is 6 below the peak price with `t − P + 1 = 2`
- **THEN** the impulse value SHALL be 1, the pullback value 3 and `ratio(pullback, impulse)` 3.

#### Scenario: Zero impulse height

- **WHEN** the origin and peak prices are equal
- **THEN** the impulse value SHALL be 0 and `ratio(pullback, impulse)` missing.
