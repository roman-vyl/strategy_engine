## Why

Research metric **C5 "who closed the gap to the anchor, price or the EMA"** (group C of the almanac, "the pullback itself").
At the wave peak `P` there is a gap between the price and the anchor EMA. By the entry the touch has closed it. C5 is the share of
that gap closed by the EMA moving: about 0 means the price came back to a flat EMA (a normal pullback), about 1 means the EMA crept up
to a price that stood still (sideways creep), above 1 means the EMA moved past the level of `P`.

Research result (weak component, a building block): the upper tail C5 ≥ 0.55 on BTC EMA500 W7 / LB 20 / SL 7 / TP 5.5 takes net from
$25.8k to $34.4k (21 base trades removed, 95 % stops); on ETH it has almost no effect, on BTC EMA1000 it does not hold. The lower tail
(the EMA barely moved) is 93–100 % stops on both tickers but only 1–3 trades per strategy.

The owner asked on 2026-10-13 for C5 as an Engine component; whether it joins the vote is decided later. The task is
`engine-tasks/c5/c5_engine_task.md`. The component is atomic: one value with an optional low and an optional high bound.

## What Changes

- **One new operand, `anchor_follow`**: `{"anchor_follow": {"episode"}}`, the value
  `C5 = g · (EMA[b] − EMA[P]) ÷ g · (peak_price − EMA[P])`.
  - `g` is +1 for a long and −1 for a short; `EMA` is the anchor (middle) EMA of the episode's stack; `P` and `peak_price` are the
    peak bar and the peak price of the current touch (the high of bar `P` for a long, the low for a short); `b` is the evaluated bar `t`.
  - Missing where there is no wave, where the gap `g · (peak_price − EMA[P])` is not greater than 0, or where an input is not finite.
    A negative C5 is a value (the EMA moved away from the price).
- **C5 as a block**: `range(anchor_follow)` with nullable bounds, `bounds exclusive`, `empty: pass`; blocked when `C5 ≤ low` or
  `C5 ≥ high`, both inclusive. The thresholds (preset high 0.55) are held by the Research manifest, not by the Engine.
- **Cost**: O(n), no pass over the bars of a leg; a spec without the operand pays nothing.

Not in this change: the vote, veto roles, catalog and manifest bindings, research surfaces, deploy.
