## ADDED Requirements

### Requirement: Completed candle operand shape

A completed candle reference SHALL be `{"completed_candle": {"episode", "timeframe", "field", "atr"}}`, all required, no other
field. `episode` SHALL be declared, `field` SHALL be `body` or `close_position`, `timeframe` SHALL be a longer multiple of the base
that divides a day or is whole weeks, `atr` SHALL be `atr_wilder` on the same timeframe. Accepted where a leg sum is, not in `change`.

#### Scenario: Malformed completed candle

- **WHEN** `atr` is missing, of another kind or on another timeframe, `field` is unknown, `timeframe` is the base timeframe, or a
  field is unknown
- **THEN** static validation SHALL reject the spec.

### Requirement: Completed candle value

At bar `t` the completed candle SHALL be the candle before the one that contains `t`, built from base bars (first open, last close,
highest high, lowest low; UTC days, weeks from Monday). With `g` +1 long, −1 short: `body` SHALL be `g · (close − open) / atr`, `atr`
the Wilder ATR one candle earlier; `close_position` SHALL be `(close − low) / range` long, `(high − close) / range` short.

#### Scenario: Strong yesterday for a long

- **WHEN** yesterday opened at 100, closed at 104 with high 105 and low 95, and the ATR of the day before yesterday is 2
- **THEN** on the long side `body` SHALL be 2 and `close_position` 0.9; on the short side −2 and 0.1.

#### Scenario: Weeks start on Monday

- **WHEN** a base bar opens on Sunday 23:55 UTC and the next on Monday 00:00 UTC
- **THEN** they SHALL belong to different weekly candles.

### Requirement: Completed candle missing values

The value SHALL be missing without a valid wave of the current touch, on bars of the first candle of the frame, when a price is not
finite, or when the ATR (body) or the range (close position) is not finite or not above 0. Bars of the candle of `t` SHALL NOT be
read.

#### Scenario: No look-ahead

- **WHEN** any price of the candle that contains `t` or a later bar changes
- **THEN** the value at `t` SHALL NOT change.

### Requirement: Monday weekly feature candles

A feature on a weekly timeframe SHALL be computed on candles that start on Monday 00:00 UTC, and the value of the last completed
weekly candle SHALL reach the base bars from the next Monday 00:00 UTC.

#### Scenario: Weekly close aligned

- **WHEN** a weekly feature is the candle close
- **THEN** every base bar of a week SHALL see the close of the previous Monday-to-Sunday week, and bars of the first week SHALL see
  none.
