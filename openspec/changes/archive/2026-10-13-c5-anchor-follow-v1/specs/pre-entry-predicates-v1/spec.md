## ADDED Requirements

### Requirement: Anchor follow operand shape

An anchor follow reference SHALL be `{"anchor_follow": {"episode"}}`; `episode` is required and no other field is allowed.
`episode` SHALL name an episode declared in `raw_spec.ema_stack_episode`. It SHALL be accepted as a side of a `ratio`, as the operand
of a `range` and of a `compare`, and rejected as the operand of a `change`.

#### Scenario: Malformed anchor follow

- **WHEN** an anchor follow names an undeclared episode, lacks `episode` or has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Anchor follow value

On each bar `t`, for the evaluated side with `g` = +1 on the long side and −1 on the short side, `P` the peak bar and `peak_price` the
peak price of the current touch of the episode (the high of bar `P` on the long side and the low on the short side), and `EMA` the
anchor EMA of the episode's stack, the value SHALL be `g · (EMA[t] − EMA[P]) ÷ g · (peak_price − EMA[P])`. It SHALL be missing when
the current touch has no valid wave, when the denominator is not greater than 0, or when `EMA[t]`, `EMA[P]` or `peak_price` is not
finite. A negative value SHALL stay a value. Bars after `t` SHALL NOT be read.

#### Scenario: Long side

- **WHEN** the side is long, `peak_price` 110, `EMA[P]` 100 and `EMA[t]` 104
- **THEN** the value SHALL be 0.4.

#### Scenario: Short side mirror

- **WHEN** the side is short, `peak_price` (the low of bar `P`) 90, `EMA[P]` 100 and `EMA[t]` 96
- **THEN** the value SHALL be 0.4.

#### Scenario: EMA moved away

- **WHEN** the side is long, `peak_price` 110, `EMA[P]` 100 and `EMA[t]` 98
- **THEN** the value SHALL be −0.2.

#### Scenario: No gap

- **WHEN** the denominator is 0 or negative
- **THEN** the value SHALL be missing.

### Requirement: Anchor follows the stack

The anchor EMA SHALL be the anchor (middle) EMA of the stack on which the episode is built, so that the value follows the stack
without a separate period in the operand.

#### Scenario: Two stacks

- **WHEN** one episode is declared on the stack 200 / 500 / 1000 and another on 500 / 1000 / 2000
- **THEN** the first SHALL read EMA500 and the second EMA1000.

### Requirement: Anchor follow filter

`range(anchor_follow)` with `bounds` `exclusive` and `empty: pass` SHALL block an entry when the value is not greater than `min` or
not less than `max` (both inclusive), each bound optional. A missing value SHALL pass.

#### Scenario: Threshold

- **WHEN** the value equals `min` or equals `max`
- **THEN** the entry SHALL be blocked.

#### Scenario: Missing value

- **WHEN** there is no wave or the denominator is not greater than 0
- **THEN** the entry SHALL pass.
