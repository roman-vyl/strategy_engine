## Why

Research metric **D1 "where the forming daily candle stands"** (group D of the almanac): how far the price at the evaluated bar has
moved from the open of the current UTC day, in daily ATRs, signed by the trade side.

In **vote B** for EMA200 it votes with weight 0.8564 at D1 ≤ −0.274, on all three coins. Reviewed with the owner on 2026-10-22
(threshold sweep, 4h and 12h variants, random-cut check); the owner asked to build it exactly as the simulation computes it.

## What Changes

- **New operand `forming_candle`** `{episode, timeframe, atr}`: `g · (close[t] − open of the forming candle of `timeframe`) / ATR`,
  the ATR being the Wilder ATR of the last completed candle of that timeframe, `g` +1 long and −1 short. Missing without a valid
  wave of the current touch (as research computes it only on entries with a wave) or without a positive ATR.
- **D1** in vote B is `forming_candle {timeframe 1d, atr {kind atr_wilder, period 14, timeframe 1d}}` with the step
  `−0.274 → 0.8564` (`at_most`) in its config. The Engine holds no threshold.
- **Cost**: O(bars), vectorised; a spec without the operand pays nothing.

Not in this change: A5, catalog and manifest bindings, deploy.
