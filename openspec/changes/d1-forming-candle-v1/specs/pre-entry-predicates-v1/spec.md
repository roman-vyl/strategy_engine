## ADDED Requirements

### Requirement: Forming candle operand shape

A forming candle reference SHALL be `{"forming_candle": {"episode", "timeframe", "atr"}}`; all are required and no other field is
allowed. `episode` SHALL name a declared episode; `timeframe` SHALL be longer than the base timeframe, a multiple of it and a divisor
of a day; `atr` SHALL be a feature request of kind `atr_wilder` on the same timeframe. It SHALL be accepted where a leg sum is
accepted and rejected as the operand of a `change`.

#### Scenario: Malformed forming candle

- **WHEN** `atr` is missing, of another kind or on another timeframe, `timeframe` is the base timeframe, or a field is unknown
- **THEN** static validation SHALL reject the spec.

### Requirement: Forming candle value

On a bar `t` with a valid wave of the current touch, the value SHALL be `g · (close[t] − open) / atr`, where `open` is the open of
the first base bar of the candle of `timeframe` that contains `t`, `atr` is the ATR of the last completed candle before it, and `g`
is +1 on the long side and −1 on the short side. It SHALL be missing without a valid wave, or when a price is not finite or the ATR
is not finite or not above 0. Bars after `t` SHALL NOT be read.

#### Scenario: Day moved against a long

- **WHEN** the day opened at 100, the close of `t` is 98 and the ATR of the previous day is 4, on the long side
- **THEN** the value SHALL be −0.5, and on the short side 0.5.

#### Scenario: ATR not yet defined

- **WHEN** fewer completed candles than the ATR period precede the candle of `t`
- **THEN** the value SHALL be missing.
