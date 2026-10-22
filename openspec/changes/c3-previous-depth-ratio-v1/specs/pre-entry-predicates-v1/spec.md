## MODIFIED Requirements

### Requirement: Pullback depth operand shape

A pullback depth reference SHALL be `{"pullback_depth": {"episode", "touch"}}`; `episode` is required and SHALL name a declared
episode, `touch` is optional, `current` (default) or `previous`, and no other field is allowed. It SHALL be accepted where a leg sum
is accepted and rejected as the operand of a `change`.

#### Scenario: Malformed pullback depth

- **WHEN** `episode` is missing or undeclared, `touch` is neither `current` nor `previous`, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

## ADDED Requirements

### Requirement: Previous pullback depth value

With `touch: previous`, on a bar `t` whose current touch has a valid wave and a previous touch row in the same episode, the value
SHALL be `g · (P0_price − ext0) / |P0_price − S0_price|`, where `S0`, `P0` are the origin and peak of the previous touch row and
`ext0` is the lowest low (long) or highest high (short) of the bars `P0..S*`, `S*` the origin of the current touch.

#### Scenario: Previous depth

- **WHEN** on the long side the previous origin price is 100, the previous peak price 110 and the lowest low of `P0..S*` is 108
- **THEN** the value SHALL be 0.2.

### Requirement: Previous pullback depth missing cases

The previous depth SHALL be missing on the first touch of an episode, when `S* ≤ P0`, when the previous impulse height is 0 or a
price of `P0..S*` is not finite. Bars after `t` SHALL NOT be read.

#### Scenario: Zero previous height

- **WHEN** the previous origin and peak prices are equal
- **THEN** the value SHALL be missing.

#### Scenario: First touch

- **WHEN** the current touch is the first of its episode
- **THEN** the value SHALL be missing.

### Requirement: Depth ratio to the previous pullback

`ratio(pullback_depth, pullback_depth touch previous, right_floor)` SHALL be missing when either value is missing or the previous
depth is not greater than `right_floor`.

#### Scenario: Three times deeper

- **WHEN** the current depth is 0.6 and the previous 0.2 with `right_floor` 1e-6
- **THEN** the ratio SHALL be 3.
