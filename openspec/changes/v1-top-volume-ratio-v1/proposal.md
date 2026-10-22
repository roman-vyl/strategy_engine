## Why

Research metric **V1.4 "the largest volumes of the pullback against those of the impulse"** (group V of the almanac): the mean volume
of the top 10 % bars of the pullback divided by the same mean of the impulse.

In **vote B** for EMA200 it is a veto at V1.4 ≤ 0.084. On the working zones it cuts 6 entries (BTC 3, ETH 2, SOL 1), 94–100 % stops.
Meaning reviewed with the owner on 2026-10-22: a degenerate wave opposite to V1.1's, an "impulse" of 2–34 bars made by one or two
volume blasts, followed by a quiet slide of 120–350 bars to the EMA. The owner builds every vote B component in the Engine so that
research simulations run from the front.

## What Changes

- **New operand `leg_top_mean`** `{episode, leg, field, share}`: the mean of the `k` largest values of a base-bar field over one leg
  of the current touch, `k = max(1, ceil(share · L))` in float64, `L` the number of bars of the leg.
  - Legs as `leg_sum`/`leg_mean`: impulse `[S*, P]`, pullback `[P+1, t]`. `field` is `volume`. `share` is a number in (0, 1], from
    the strategy config (research 0.1).
  - Missing where there is no valid wave, the leg is empty or a value of the leg is not finite.
- **V1.4**: `ratio(leg_top_mean(pullback), leg_top_mean(impulse))`; a zero impulse value makes the ratio missing.
- **Cost**: the impulse value once per touch, the pullback value incrementally per touch on bars with a valid wave; a spec without
  the operand pays nothing.

Not in this change: the other vote B components, catalog and manifest bindings, deploy.
