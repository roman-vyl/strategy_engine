# htf-candle-shape-v1 Specification

## Purpose
Higher-timeframe candle shape features: the body of a candle over the Wilder ATR of the candle before it, and the position of its close in its range, on any feature timeframe (weeks from Monday 00:00 UTC), seen by base bars as the value of the last completed candle.
## Requirements
### Requirement: Candle body over the previous ATR

A feature of kind `candle_body_atr` with an integer `period ≥ 1` and source `close` SHALL give, on every candle of its timeframe,
`(close − open) / atr_wilder(period)` of the previous candle, missing while that ATR is missing or not above 0. On a higher timeframe
the base bars SHALL see the value of the last completed candle.

#### Scenario: Strong yesterday

- **WHEN** yesterday opened at 100 and closed at 104 and the Wilder ATR of the day before yesterday is 2
- **THEN** every base bar of today SHALL see `candle_body_atr 1d` = 2.

### Requirement: Candle close position

A feature of kind `candle_close_position` with source `close` and no parameters SHALL give, on every candle of its timeframe,
`(close − low) / (high − low)`, missing when `high − low` is not above 0. On a higher timeframe the base bars SHALL see the value of
the last completed candle.

#### Scenario: Close near the high

- **WHEN** yesterday's high is 105, low 95 and close 104
- **THEN** every base bar of today SHALL see `candle_close_position 1d` = 0.9.

#### Scenario: Malformed request

- **WHEN** `candle_close_position` carries a parameter or another source, or `candle_body_atr` has no positive integer period
- **THEN** the request SHALL be rejected.

### Requirement: Monday weekly candles

Features on a weekly timeframe SHALL be computed on candles that start on Monday 00:00 UTC, and the value of a completed week SHALL
reach the base bars from the next Monday 00:00 UTC.

#### Scenario: Weekly close aligned

- **WHEN** a weekly feature is read on a base bar of a week
- **THEN** it SHALL be the value of the previous Monday-to-Monday week, and bars of the first week SHALL see none.

### Requirement: Candle shape warm-up

The live history SHALL cover `candle_body_atr` as `atr_wilder` of the same period plus one candle, and `candle_close_position` as
one candle of its timeframe.

#### Scenario: Live window for a daily body

- **WHEN** a live spec reads `candle_body_atr 1d` with period 14
- **THEN** the history requirement SHALL be one daily candle more than `atr_wilder 1d` with period 14.

