## Context

- Research (`/mnt/project-files/ema200_calib/review/d1sweep/`): `combo3.py` `days()` + `d1v_feat.py` (D1v) and `week.py` `weeks()` +
  `wk_feat.py` (Wk). 5m candles grouped by UTC day, or by week `(day + 3) // 7` (Monday start); open of the first bar, close of the
  last, high/low over the candle; true range with the previous close (`h − l` for the first candle); Wilder ATR seeded at candle 13
  with the mean of the first 14 true ranges. For an entry in candle `kk`, `p = kk − 1`: `body = G · (C[p] − O[p]) / atr[p − 1]`,
  `pos = (C[p] − L[p]) / (H[p] − L[p])` long, `(H[p] − C[p]) / (H[p] − L[p])` short.
- The Engine reads only base candles from MDS. Every higher-timeframe feature (EMA, ATR, ADX on 1h/4h/1d) is computed on candles
  aggregated from them (`resample_ohlcv`) and aligned as the value of the last completed candle. `atr_wilder` equals the research
  ATR (OpenSpec `b1-candle-ratio-v1`, D5).

## Decisions

### D1. Two plain indicator kinds

`candle_body_atr` and `candle_close_position` are feature kinds like `atr_wilder`: a contract entry in `feature_kinds`, a math
branch in the range evaluator, a warm-up policy. They work on any timeframe, base included, and need no episode. On the feature
timeframe, candle `i` gets `(C[i] − O[i]) / atr[i − 1]` and `(C[i] − L[i]) / (H[i] − L[i])`; the alignment moves candle `i` to the
base bars of candle `i + 1`, which is exactly research's `p = kk − 1` and `atr[p − 1]`.

Rejected: an operand that rebuilds candles from base bars inside the predicate layer (first draft): it duplicated the HTF path.

### D2. Side outside the feature

A feature has no side. The long/short reading is the predicate's `short` override or the vote config: body sign flips, close
position `x` on a long equals `1 − x` on a short. Research's `(H − C)/(H − L)` equals `1 − (C − L)/(H − L)` up to rounding (checked
on all EMA200 entries, see tasks).

### D3. Monday weeks

pandas `"1W"` is `W-SUN`, which with left-closed left-labelled bins starts weeks on Sunday. `Nw` now maps to `N W-MON`, and the
alignment shifts by `timeframe_duration_ms` (an anchored weekly offset would roll to its anchor day). For minutes, hours and days the
fixed duration equals the old offset, so no existing value changes.

### D4. Missing values

`candle_body_atr` is missing while the previous candle's ATR is missing or not above 0; `candle_close_position` is missing on a
candle without range. Base bars of the first candle see no value.
