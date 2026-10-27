# rolling-extreme-feature-v1 Specification

## Purpose
Rolling maximum and minimum of a base-bar field (OHLC or open interest) over the last N bars as plain features, used by the W8 open-interest voters of EMA200.

## Requirements

### Requirement: Rolling maximum and minimum

A feature of kind `rolling_max` or `rolling_min` with an integer `period ≥ 1` and a `source` in `open`, `high`, `low`, `close`,
`open_interest` (default `close`) SHALL give, on every candle of its timeframe, the maximum or minimum of the source over the last
`period` candles, the current one included. It SHALL be missing until the window holds `period` finite values. On a higher
timeframe the base bars SHALL see the value of the last completed candle.

#### Scenario: Thirty days of open interest

- **WHEN** `rolling_max` has source `open_interest` and period 8640 on 5m bars, and the OI peaked at 120 000 within the last 8640 bars
- **THEN** the value on the current bar SHALL be 120 000.

#### Scenario: Short history

- **WHEN** fewer than `period` bars with open interest exist up to the current bar
- **THEN** the value SHALL be missing.

### Requirement: Rolling extreme request shape

A request SHALL carry exactly the `period` parameter. A missing or non-positive `period`, another parameter or an unknown source
SHALL be rejected. The label SHALL carry the source.

#### Scenario: Malformed rolling request

- **WHEN** `rolling_max` has period 0, an extra parameter, or source `volume`
- **THEN** the request SHALL be rejected.
