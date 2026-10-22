## ADDED Requirements

### Requirement: Leg efficiency operand shape

A leg efficiency reference SHALL be `{"leg_efficiency": {"episode", "leg"}}`; both are required and no other field is allowed.
`episode` SHALL name a declared episode and `leg` SHALL be `impulse` or `pullback`. It SHALL be accepted where a leg sum is accepted
and rejected as the operand of a `change`.

#### Scenario: Malformed leg efficiency

- **WHEN** `leg` is missing or neither `impulse` nor `pullback`, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg efficiency value

On a bar `t` with a valid wave of the current touch, the value SHALL be `|close[z] − close[a]| / Σ |close[k] − close[k−1]|` over
`k = a+1..z`, with `a = S*, z = P` for the impulse and `a = P, z = t` for the pullback. It SHALL be missing without a valid wave,
when `z ≤ a`, when the sum is 0, or when a close of `[a, z]` is not finite. Bars after `t` SHALL NOT be read.

#### Scenario: Straight pullback, crooked impulse

- **WHEN** the impulse closes go 100, 103, 101, 104 and the pullback closes go 104, 102, 100
- **THEN** the impulse value SHALL be 0.5, the pullback value 1 and `ratio(pullback, impulse)` 2.

#### Scenario: Pullback of one bar

- **WHEN** the evaluated bar is the peak bar
- **THEN** the pullback value SHALL be missing.
