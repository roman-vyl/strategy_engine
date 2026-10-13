## MODIFIED Requirements

### Requirement: Leg mean operand shape

A leg mean reference SHALL be `{"leg_mean": {"episode", "leg", "field"}}`; all three are required and no other field is allowed.
`episode` SHALL name an episode declared in `raw_spec.ema_stack_episode`, `leg` SHALL be `impulse` or `pullback` and `field` SHALL be
`volume`, `force_with` or `force_against`. It SHALL be accepted as a side of a `ratio`, as the operand of a `range` and of a
`compare`, and rejected as the operand of a `change`.

#### Scenario: Malformed leg mean

- **WHEN** a leg mean names an undeclared episode, an unknown `leg` or `field`, lacks a required field or has an unknown field
- **THEN** static validation SHALL reject the spec.

## ADDED Requirements

### Requirement: Candle force series

For the field `force_with` or `force_against` the series averaged by a leg mean SHALL be the candle force on the base bars,
`F[u] = (close[u] − close[u−1]) × volume[u]`, multiplied by `+1` for `force_with` on the long side and `force_against` on the short side
and by `−1` for `force_against` on the long side and `force_with` on the short side. The series SHALL be missing on bar 0 and wherever
`close[u]`, `close[u−1]` or `volume[u]` is not finite. The leg mean of it SHALL be the arithmetic mean over all bars of the leg, with the legs
and the missing rules of the leg mean operand. The impulse leg `[S*, P]` SHALL read `close[S*−1]` for its first bar.

#### Scenario: Long side

- **WHEN** the side is long and a pullback bar closes 2 below the previous close on volume 10
- **THEN** its `force_against` SHALL be 20 and its `force_with` SHALL be −20.

#### Scenario: Short side mirror

- **WHEN** the side is short and a bar closes 2 above the previous close on volume 10
- **THEN** its `force_against` SHALL be 20.

#### Scenario: First bar of the series

- **WHEN** the impulse leg starts at bar 0
- **THEN** its mean SHALL be missing.

### Requirement: Force ratio filter

`range(ratio(leg_mean(pullback, force_against), leg_mean(impulse, force_with)))` with `bounds` `exclusive` and `empty: pass` SHALL
block an entry when the ratio is not greater than `min` or not less than `max` (both inclusive), each bound optional. A missing ratio SHALL
pass. The ratio SHALL be missing when the impulse mean is not greater than 0 or either mean is missing. A negative pullback mean SHALL
stay a value. Bars after the evaluated bar SHALL NOT be read.

#### Scenario: Impulse without force

- **WHEN** the impulse mean force with the trade is 0 or negative
- **THEN** the ratio SHALL be missing and the entry SHALL pass.

#### Scenario: Threshold

- **WHEN** the ratio equals `min` or equals `max`
- **THEN** the entry SHALL be blocked.

#### Scenario: Pullback in favour of the trade

- **WHEN** the pullback mean force against the trade is negative and `min` is 0
- **THEN** the ratio SHALL be negative and the entry SHALL be blocked by `min`.
