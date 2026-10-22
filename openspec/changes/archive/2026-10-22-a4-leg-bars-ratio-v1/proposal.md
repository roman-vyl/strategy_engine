## Why

Research metric **A4 "how many times longer the pullback is than the impulse"** (group A of the almanac): the number of bars of the
pullback `P..t` over the number of bars of the impulse `S*..P`.

In **vote B** for EMA200 it votes with weight 0.15 at A4 ≥ 10.3 (threshold set by the owner). On the working zones it cuts 10 / 7 / 2
entries (BTC / ETH / SOL, stops 80 / 70 / 100 % against a base of 76 / 78 / 75 %). Reviewed with the owner on 2026-10-22: a pullback
ten times longer than its impulse is a fading trend, not a pullback.

## What Changes

- **New operand `leg_bars`** `{episode, leg}`, the number of base bars of one leg of the current touch, both ends inclusive:
  `impulse` `P − S* + 1`, `pullback` `t − P + 1` (the bar `P` in both legs, as `leg_speed` and research).
  Missing where there is no valid wave.
- **A4** is `ratio(leg_bars(pullback), leg_bars(impulse))`; vote B puts `10.3 → 0.1491` into its config. The Engine holds no threshold.
- **Cost**: O(bars), vectorised; a spec without the operand pays nothing.

Not in this change: A5, D1, catalog and manifest bindings, deploy.
