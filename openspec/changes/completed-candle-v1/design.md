## Context

- Research references (`/mnt/project-files/ema200_calib/review/`):
  - D1v: `d1sweep/combo3.py` `days()` and `d1sweep/d1v_feat.py`. 5m bars grouped by UTC day, open of the first bar, close of the
    last, high/low over the day; daily true range with the previous day close (`h − l` for the first day); ATR seeded at day 13
    with the mean of the first 14 true ranges, then Wilder. For an entry in day `kk`, yesterday is `p = kk − 1`:
    `body = G · (C[p] − O[p]) / atr[p − 1]`, `pos = (C[p] − L[p]) / (H[p] − L[p])` long, `(H[p] − C[p]) / (H[p] − L[p])` short.
    `D1v = D1 if body ≥ 1 and pos ≥ 0.85 else 9`.
  - Wk: `d1sweep/week.py` `weeks()` and `d1sweep/wk_feat.py`: the same with weeks `(day + 3) // 7` (Monday start), `Wk = body`.
- The Engine's `atr_wilder` equals the research ATR (OpenSpec `b1-candle-ratio-v1`, D5; checked again for days in
  `d1-forming-candle-v1`). Its higher-timeframe value is aligned to every base bar as the value of the last completed candle.

## Decisions

### D1. Operand `completed_candle`

`{"completed_candle": {"episode", "timeframe", "field", "atr"}}`, all required. `timeframe` SHALL be longer than the base timeframe,
a multiple of it, and either a divisor of a day or whole weeks. `atr` SHALL be `atr_wilder` on the same timeframe. The candles are
built from the base bars of the frame: bucket `time // timeframe` for divisors of a day, `(time + 3 days) // timeframe` for weeks.
At bar `t` the completed candle is the bucket before the bucket of `t`. The ATR of the candle before it is the aligned feature value
on the last base bar of the completed candle, which needs no second feature.

Rejected: a `lag` on `forming_candle`. The forming candle reads `close[t]`; the completed candle reads a whole closed candle and its
range, and is normalised by the ATR one candle earlier.

### D2. Monday weeks

pandas `"1W"` is `W-SUN`; with left-closed left-labelled bins it starts weeks on Sunday. `1w` (and `Nw`) now map to `W-MON`, and the
completed candle is shifted by `timeframe_duration_ms` (an anchored weekly offset would roll to its anchor day). For minutes, hours
and days the fixed duration is the same offset as before, so no existing value changes.

### D3. Wave gate

As `forming_candle`: missing on bars without a valid wave of the current touch, so the vote input is silent there. Research computes
yesterday's body on every entry; entries without a wave are not eligible in research either (D1 is missing there).

### D4. D1v stays a composition

D1v is `forming_candle 1d` gated by two `completed_candle 1d` conditions. The gate belongs to the vote module (owner rule: components
atomic, roles in the vote). It is specified with the W8 vote module, not here.

### D5. Identity

Own node family `predicate.completed_candle` with params `timeframe` and `field`, upstream the episode and the ATR column.
