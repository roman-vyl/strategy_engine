## Why

Research metric **B3 "how big the impulse was"** (group B of the almanac): the impulse height `|P − S*|` in units of the average
candle, the rolling-mean ATR over 48 base bars read on the peak bar `P`.

In **vote B** for EMA200 it votes with weight 0.32 at B3 ≤ 9.59 and vetoes at B3 ≤ 4.65. On the working zones the vote cuts 55 / 32 / 7
entries (BTC / ETH / SOL, stops 77 / 85 / 86 % against a base of 76 / 78 / 75 %), the veto 1 / 5 / 1 entries, all stops. Reviewed with
the owner on 2026-10-22: a small impulse is noise, not a trend.

## What Changes

- **New operand `impulse_atr`** `{episode, atr}`: `|peak_price − origin_price| / atr[P]` on every bar with a valid wave of the current
  touch, `atr` a required base-timeframe feature of kind `atr` (rolling-mean true range) whose period comes from config (research 48).
  - Missing where there is no valid wave, a price is not finite or `atr[P]` is not finite or not above 0. A zero height gives 0.
- **B3** is this operand; vote B puts `9.59 → 0.32` and `4.65 → veto` into its config. The Engine holds no threshold.
- **Cost**: O(bars); the ATR column is the shared feature node, a spec without the operand pays nothing.

Not in this change: the other vote B components, catalog and manifest bindings, deploy.
