## Context

- Research reference: `btc_recheck/code/altvals.py`, `tf_frame(1440)` and key `d1_1d`. 5m bars are grouped by UTC day; the day
  open is the open of its first bar; the daily true range uses the previous day close (`h − l` for the first day); the ATR is
  seeded at day 13 with the mean of the first 14 true ranges, then Wilder. `D1 = G · (C[t] − open of the day of t) / atr[day − 1]`,
  missing when the previous day index is below 14, the ATR is not positive, or the entry has no wave.
- The Engine already resamples a feature to a higher timeframe and aligns the value of the last completed candle to every base bar
  (`align_completed_to_base`); `atr_wilder` is the research ATR (OpenSpec `b1-candle-ratio-v1`, D5).

## Decisions

### D1. Operand `forming_candle`

`{"forming_candle": {"episode", "timeframe", "atr"}}`, all required. `timeframe` SHALL be longer than the base timeframe, a multiple
of it and a divisor of a day. `atr` SHALL be `atr_wilder` on the same timeframe. The forming candle of `t` is the bucket of
`time[t] // timeframe` on the UTC grid; its open is the open of its first base bar; `close[t]` is the close of `t` itself. The ATR
read at `t` is the aligned feature value, which is the ATR of the last completed candle.

Rejected: reusing `candle` with a new leg. `candle` measures candles of a leg; D1 does not depend on the wave except as a gate.

### D2. Wave gate

Research computes D1 only on entries with a wave; the operand is missing on bars without a valid wave of the current touch, so a
vote input stays silent there as in research.

### D3. Warm-up

Research also requires at least 15 completed days (`kp ≥ 14`), one day more than the ATR seed. No research entry falls on that
day (checked on BTC, ETH, SOL); the operand follows the ATR warm-up only.

### D4. Identity

Own node family `predicate.forming_candle` with param `timeframe`, upstream the episode and the ATR column.
