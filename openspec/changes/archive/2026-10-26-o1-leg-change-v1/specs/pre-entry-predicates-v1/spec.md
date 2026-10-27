## ADDED Requirements

### Requirement: Leg change operand shape

A leg change reference SHALL be `{"leg_change": {"episode", "leg", "field", "touch"}}`; `episode` (a declared episode), `leg`
(`impulse` | `pullback`) and `field` (`close` | `open_interest`) are required, `touch` (`current` | `previous`) defaults to
`current` and `previous` SHALL be allowed only with `impulse`. No other field is allowed.

#### Scenario: Malformed leg change

- **WHEN** `field` is `volume`, or `touch` is `previous` with `leg` `pullback`, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg change placement

A leg change SHALL be accepted where a leg sum is accepted and rejected as the operand of a `change`.

#### Scenario: Leg change inside change

- **WHEN** a `change` operand is a leg change
- **THEN** static validation SHALL reject the spec.

### Requirement: Leg change value

On a bar `t` the value SHALL be `100 * (x[end] / x[begin] - 1)` of the base-bar field `x`, with `(begin, end)` `(S*, P)` of the
current touch for `impulse`, `(P, t)` for `pullback`, and `(S*, P)` of the previous touch of the same episode for `impulse` with
`touch` `previous`. It SHALL be missing when there is no valid wave or no previous touch, when either value is not finite, or when
`x[begin] <= 0`. Bars after `t` SHALL NOT be read.

#### Scenario: Open interest falls over the impulse

- **WHEN** the open interest is 1000 at `S*` and 940 at `P`
- **THEN** the impulse value over `open_interest` SHALL be −6 on every bar of that touch.

#### Scenario: Missing open interest at the peak

- **WHEN** the bar `P` has no open interest
- **THEN** the impulse value over `open_interest` SHALL be missing.
