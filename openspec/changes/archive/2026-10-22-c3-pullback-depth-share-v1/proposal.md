## Why

Research metric **C3.1 "how much of the rise the pullback gave back"** (group C of the almanac): the depth of the pullback, from the
peak `P` to its extreme up to the evaluated bar, as a share of the impulse height `|P − S*|`.

In **vote B** for EMA200 it votes with weight 0.41 at C3.1 ≥ 0.604. On the working zones it cuts 132 entries (BTC 74, ETH 43,
SOL 15), stops 78.6 / 88.5 / 77.7 % against a base of 75.6 / 78.4 / 74.5 %. Reviewed with the owner on 2026-10-22: the depth is
measured by the extreme price of the pullback (low for long, high for short), as in the research simulation.

## What Changes

- **New operand `pullback_depth`** `{episode}`: on every bar `t` with a valid wave of the current touch,
  `g · (peak_price − ext) / |peak_price − origin_price|`, `ext` the lowest low (long) or highest high (short) of the bars `[P, t]`,
  `g` +1 long and −1 short.
  - `origin_price` and `peak_price` are the touch-table prices already used by A1, B1, V1.3 and C5.
  - Missing where there is no valid wave, the impulse height is 0 or a price of `[P, t]` is not finite.
- **C3.1** is this operand; vote B puts `0.604 → weight` into its config. The Engine holds no threshold.
- **Cost**: one pass over the bars with a valid wave, the extreme kept incrementally per touch; a spec without the operand pays
  nothing.

Not in this change: C3.2 (the same depth of the previous wave, next change), the other vote B components, catalog and manifest
bindings, deploy.
