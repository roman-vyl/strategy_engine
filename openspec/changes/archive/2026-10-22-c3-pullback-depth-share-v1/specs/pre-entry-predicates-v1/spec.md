## ADDED Requirements

### Requirement: Pullback depth operand shape

A pullback depth reference SHALL be `{"pullback_depth": {"episode"}}`; `episode` is required, SHALL name a declared episode, and no
other field is allowed. It SHALL be accepted where a leg sum is accepted and rejected as the operand of a `change`.

#### Scenario: Malformed pullback depth

- **WHEN** `episode` is missing or undeclared, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Pullback depth value

On a bar `t` with a valid wave of the current touch, the value SHALL be `g · (peak_price − ext) / |peak_price − origin_price|`,
where `ext` is the lowest low of the bars `P..t` on the long side and the highest high on the short side, `g` is +1 long and −1
short. It SHALL be missing when the touch has no valid wave, the impulse height is 0 or a price of `P..t` is not finite. Bars after
`t` SHALL NOT be read.

#### Scenario: Long depth

- **WHEN** on the long side the origin price is 100, the peak price 110 and the lowest low of `P..t` is 103
- **THEN** the value SHALL be 0.7.

#### Scenario: Short depth

- **WHEN** on the short side the origin price is 110, the peak price 100 and the highest high of `P..t` is 104
- **THEN** the value SHALL be 0.4.
