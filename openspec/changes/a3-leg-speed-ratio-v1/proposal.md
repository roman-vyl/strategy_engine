## Why

Research metric **A3 "how many times faster the pullback is than the impulse"** (group A of the almanac): the price distance per bar
of the pullback, from the peak `P` to the close of the evaluated bar, over the price distance per bar of the impulse `S*..P`.

In **vote B** for EMA200 it votes with weight 0.39 at A3 ≥ 3.33 and vetoes at A3 ≥ 15.8. On the working zones the vote cuts 22 / 29 / 9
entries (BTC / ETH / SOL, stops 78 / 82 / 89 % against a base of 76 / 78 / 75 %), the veto 2 / 1 / 2 entries, all stops. Reviewed
with the owner on 2026-10-22: a sharp counter move means a strong seller against the trend.

## What Changes

- **New operand `leg_speed`** `{episode, leg}`, the price distance per bar of one leg of the current touch:
  - `impulse`: `|peak_price − origin_price| / (P − S* + 1)`;
  - `pullback`: `|peak_price − close[t]| / (t − P + 1)`, the bar `P` counted in both legs as in research.
  - Missing where there is no valid wave or a price is not finite.
- **A3** is `ratio(leg_speed(pullback), leg_speed(impulse))`; a zero impulse height makes it missing. Vote B puts `3.33 → 0.3891`
  and `15.8 → veto` into its config. The Engine holds no threshold.
- **Cost**: O(bars), vectorised; a spec without the operand pays nothing.

Not in this change: the other vote B components, catalog and manifest bindings, deploy.
