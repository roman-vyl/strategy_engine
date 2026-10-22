## Why

Research metric **V1.2 "own-colour volume of the pullback against the impulse"** (group V of the almanac). For a long it is the
volume of the red candles of the pullback divided by the volume of the green candles of the impulse; for a short the colours swap.
It is V1.1 counted only on candles that move the way their leg moves.

In **vote B** for EMA200 it is a veto at V1.2 ≤ 0.0422. On the working zones it cuts 2 entries per coin (BTC, ETH, SOL), all stops,
and all 6 are already vetoed by V1.1. The owner decided on 2026-10-22 to build every vote B component in the Engine anyway, so that
any research simulation can run from the front; whether a component is used is decided later.

## What Changes

- **`leg_sum` gains the field `own_color_volume`** (operand of `v1-volume-sum-ratio-v1`): the volume of the leg's bars whose candle
  has the leg's own colour, 0 for the other bars.
  - Impulse `[S*, P]`: bars with `close > open` on the long side and `close < open` on the short side (with the trade).
  - Pullback `[P+1, t]`: bars with `close < open` on the long side and `close > open` on the short side (against the trade).
  - A bar with `close = open` never counts. The legs and missing rules are those of `leg_sum`; a non-finite open, close or volume
    of a leg bar makes the value missing.
- **V1.2**: `ratio(leg_sum(pullback, own_color_volume), leg_sum(impulse, own_color_volume))`. A zero impulse sum makes the ratio
  missing. Levels and the veto come only from the strategy config.
- **Cost**: O(n) per side; a spec without the field pays nothing.

Not in this change: V1.4, the other vote B components, catalog and manifest bindings, deploy.
