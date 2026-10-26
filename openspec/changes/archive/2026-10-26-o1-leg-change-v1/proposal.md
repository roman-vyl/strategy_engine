## Why

Research metric **O1 "open interest over the impulse"** of vote W8 for EMA200: the percent change of open interest from the impulse
start `S*` to the peak `P`. A falling OI while the price runs to the peak means closing positions made the impulse (short covering or
liquidations), not new money. Discussed with the owner on 2026-10-26 (15:59, «Да»): a new universal operand in the same family as
the leg mean and leg sum, over any base-bar field (price, now open interest).

The OI value of a bar follows the Engine rule approved in SE PR #48: the base 5m bar carries the Bybit 5min OI of its open. The
research reference was recomputed under this rule (owner 15:53 «Запрашивай»):
`/mnt/project-files/ema200_calib/review/oi5/engine_rule/` (`O1 = 100 * (oi(P) / oi(S*) - 1)`).

## What Changes

- **New operand `leg_change`** `{episode, leg, field, touch}`: the percent change of a base-bar field between the two ends of one
  leg, `100 * (x[end] / x[begin] - 1)`. `leg` `impulse` is `S* → P`, `pullback` is `P → t`. `field` is `close` or
  `open_interest`. `touch` `current` (default) or `previous` (the impulse of the previous touch of the same episode,
  `S*₀ → P₀`; with `previous` only `impulse` is allowed).
- **O1** is `leg_change {leg: impulse, field: open_interest}`. Thresholds and weights live in the vote config; the Engine holds none.
- **Cost**: O(bars), vectorised, reads two values per bar; a spec without the operand pays nothing.

Not in this change: the other W8 voters (kI, W1, W2d, W8), the voting module, catalog and manifest bindings, deploy.
