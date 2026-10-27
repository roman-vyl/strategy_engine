## Context

- Research (5m rule): `Ser.rolling('30D').max()` over the Bybit 5min OI records, read at the record of the entry bar. The value is
  missing while `t(b) + 5m − first_record < d days`. The 5m OI series has no gaps, so a time window of d days is exactly
  `d · 288` records, and the history condition is "at least `d · 288` records up to and including the bar".
- Engine: `open_interest` is a column of the indicator frame (SE #48), NaN where a bar has none. HTF candles take the last base
  bar's OI.

## Decisions

### D1. Feature kinds

`rolling_max` / `rolling_min` with an integer `period ≥ 1` and `source` in `open`, `high`, `low`, `close`, `open_interest`
(default `close`). On the feature timeframe the value is `x.rolling(period, min_periods=period).max()` (or `.min()`), so one
missing value inside the window leaves it missing. The label carries the source, `rolling_max_<source>_<tf>_<period>`, and the
identity carries `period` and `source`. Live warm-up is `period` candles.

Rejected: a time-based window (`'30D'`). Every other Engine feature counts candles, and on a gapless grid the two are equal.

### D2. Open interest operand

The `price` operand accepts `open_interest`. It reads the bar's own value from the shared market arrays, as `close` does.
Rejected: a new operand key. `price` already means "a field of the base bar", and a second key would duplicate it.

### D3. Parity reference

`W8_14`, `W8_30` in `review/oi5/engine_rule/feat_<coin>.npz` (5m rule, full precision).
