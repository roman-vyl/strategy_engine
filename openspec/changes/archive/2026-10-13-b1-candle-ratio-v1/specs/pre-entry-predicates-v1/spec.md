## ADDED Requirements

### Requirement: Candle operand shape

A candle reference SHALL be `{"candle": {"episode", "leg", "timeframe", "direction", "atr"?}}`. `episode`, `leg`, `timeframe` and
`direction` are required and no other field is allowed. `episode` SHALL name an episode declared in `raw_spec.ema_stack_episode`.
`leg` SHALL be `impulse` or `pullback`, `direction` SHALL be `with` or `against`, and `timeframe` SHALL be a timeframe that is a
multiple of the base timeframe.

#### Scenario: Malformed candle

- **WHEN** a candle names an undeclared episode, an unknown `leg` or `direction`, a timeframe that is not a multiple of the base
  timeframe, a missing required field or an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Candle operand use

A candle reference SHALL be accepted wherever a segment reference is accepted: as a side of a `ratio`, as the operand of a `range`
and as an operand of a `compare`. It SHALL NOT be accepted as the operand of a `change`. A short override SHALL NOT replace it.

#### Scenario: Candle as change operand

- **WHEN** a `change` predicate has a candle reference as its operand
- **THEN** static validation SHALL reject the spec.

### Requirement: Candle ATR normalisation

When `atr` (feature kind `atr_wilder`, same timeframe as the candle) is present, each candle body SHALL be divided by that
candle's ATR before the maximum is taken; a candle without a positive ATR SHALL be skipped. Without `atr`, bodies are in price units.

#### Scenario: Forming candle

- **WHEN** the last candle of the pullback is still forming on the evaluated bar
- **THEN** its body SHALL be divided by the ATR of the candle before it.

#### Scenario: Closed candle

- **WHEN** a candle of the impulse ends inside the impulse
- **THEN** its body SHALL be divided by its own ATR.

#### Scenario: Different ATR timeframe

- **WHEN** `atr` has a timeframe other than the candle's `timeframe` or a kind other than `atr_wilder`
- **THEN** static validation SHALL reject the spec.

### Requirement: Candle legs

For the evaluated side's episode and the current touch of bar `t`, the `impulse` leg SHALL be the bars from the origin bar `S*`
to the peak bar `P` inclusive, and the `pullback` leg SHALL be the bars from `P+1` to `t` inclusive. Only bars up to `t` SHALL be
read. When the touch has no pullback bars (`t = P`), no active episode, or a censored episode, the value SHALL be missing.

#### Scenario: Peak bar

- **WHEN** the pullback leg is evaluated on the peak bar itself
- **THEN** the candle value SHALL be missing
- **AND** the peak bar SHALL be counted in the impulse only.

### Requirement: Candles assembled from base bars

The candles of a leg SHALL be assembled from the base bars of that leg only. Base bars SHALL be grouped by bucket on the
`timeframe` grid, aligned to the epoch with the bucket start included and the bucket end excluded. The open of a candle SHALL be
the open of its first leg bar in the bucket and the close the close of its last leg bar in the bucket that is not after `t`.
A candle SHALL therefore be clipped at the start of the leg and, for the impulse, at `P`.

#### Scenario: Edge candle

- **WHEN** a 1h bucket starts before the pullback and the pullback starts inside it
- **THEN** the candle of that bucket in the pullback SHALL open at the first pullback bar.

#### Scenario: Forming candle

- **WHEN** the bar `t` lies inside a bucket that has not ended
- **THEN** the candle of that bucket SHALL close at the close of bar `t`
- **AND** the value on the next bar SHALL take the new close without waiting for the bucket to end.

### Requirement: Candle body and direction

A candle's body with the trade SHALL be `close − open` when positive on the long side and `open − close` when positive on the
short side; its body against the trade SHALL be the opposite one. The value of the candle operand SHALL be the largest (normalised, when `atr` is set) body of the
requested direction over the candles of the leg, and 0 when no candle has a positive body in that direction. The value SHALL be
missing when an open or close that enters is not finite.

#### Scenario: Pullback without a counter candle

- **WHEN** no candle of the pullback closes against the trade
- **THEN** the value SHALL be 0, a valid value.

#### Scenario: Impulse without a with-trade candle

- **WHEN** a ratio has the impulse with-trade value as its right side and that value is 0
- **THEN** the ratio SHALL be missing on that bar
- **AND** a `range` with `empty: pass` SHALL not block the bar.

#### Scenario: Short side mirror

- **WHEN** the evaluated side is short and a candle closes above its open in the pullback
- **THEN** that candle SHALL count as against the trade.

### Requirement: Candle operand per touch

The impulse value SHALL be the same on every bar of one touch. The pullback value on bar `t` SHALL depend only on bars up to
`t`: changing any later bar SHALL NOT change it. A candle assembled from bars with gaps in the base series SHALL use only the
bars that exist.

#### Scenario: No lookahead

- **WHEN** the bars after `t` are replaced
- **THEN** the candle values on bars up to `t` SHALL be unchanged.

### Requirement: Wilder ATR feature

A feature kind `atr_wilder` SHALL exist with the single parameter `period`, source close and any timeframe. Its first true range
SHALL be `high − low`, its first value SHALL be the mean of the first `period` true ranges, and each next value SHALL be
`(previous · (period − 1) + true range) / period`; values before the first SHALL be missing. The `atr` feature SHALL be
unchanged.

#### Scenario: Seed

- **WHEN** a series has 20 candles and `period` is 14
- **THEN** the first 13 values SHALL be missing and the 14th SHALL be the mean of the first 14 true ranges.
