## ADDED Requirements

### Requirement: Own colour volume field

A leg sum MAY have `field` `own_color_volume`; a leg mean SHALL reject it. Its series on the evaluated side SHALL be `volume[u]` for a
bar whose candle has the leg's own colour and 0 otherwise. A non-finite `open`, `close` or `volume` on a leg bar SHALL make the value
missing.

#### Scenario: Missing input

- **WHEN** a pullback bar has a non-finite close
- **THEN** the own colour pullback sum SHALL be missing.

### Requirement: Own colour of a leg

On the impulse the own colour SHALL be `close > open` on the long side and `close < open` on the short side; on the pullback it
SHALL be `close < open` on the long side and `close > open` on the short side. A bar with `close = open` SHALL never count.

#### Scenario: Long pullback

- **WHEN** the side is long and the pullback has a red bar with volume 30, a green bar with volume 50 and a doji with volume 20
- **THEN** the own colour pullback sum SHALL be 30.

#### Scenario: Short impulse

- **WHEN** the side is short and an impulse bar closes below its open with volume 40
- **THEN** its volume SHALL count in the own colour impulse sum.

### Requirement: Own colour volume ratio

`ratio(leg_sum(pullback, own_color_volume), leg_sum(impulse, own_color_volume))` SHALL be missing when the impulse sum is not greater
than the ratio's `right_floor` (default 0) or either sum is missing. A pullback without a counter candle SHALL give 0, a value.

#### Scenario: Impulse without a with-trade candle

- **WHEN** no impulse bar of the long side closes above its open
- **THEN** the ratio SHALL be missing.
