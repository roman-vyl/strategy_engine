## Why

Research metric **V1.3 "mean volume per candle of the pullback against the impulse"** (group V of the almanac, volume on the
legs of the wave). Plain sums of volume depend on leg length and gave no stable result; dividing by the number of bars fixed it,
with the same sign on BTC and ETH. The useful tail is the low one (a very quiet pullback against the impulse):
BTC W7 / LB 20 / SL 7 / TP 5.5, V1.3 ≤ 0.23 takes net from $25.8k to $28.1k (31 trades cut, 90 % stops); ETH W11 / LB 20 / SL 8,
V1.3 ≤ 0.26 takes $11.2k to $15.0k (12 cut, all stops). The high tail (several times the impulse) also holds more stops.

The owner wants V1.3 as an Engine component on the same two legs as A1/A2/B1. The weighted vote is a later, separate change.

## What Changes

Builds on the A1/A2/B1 blocks (`ratio`, `range` with nullable bounds, the EMA-stack episode). No new indicator kind.

- **One new operand, `leg_mean`**: the mean of a base-bar market field over one leg of the current touch of an episode.
  - Fields: `episode`, `leg` (`impulse` or `pullback`), `field` (only `volume`, the volume of the base bars).
  - Impulse = bars `[S*, P]`, pullback = bars `[P+1, t]`, both ends inclusive (as B1; A1/A2 pullbacks start at `P`, so the operand
    has its own two legs). `t` is the evaluated bar, nothing after it is read.
  - Missing where there is no wave, where the leg is empty (`t = P` for the pullback) or the volume is not finite.
- **V1.3 as a block**: `ratio(leg_mean(pullback), leg_mean(impulse))` in a `range` with nullable bounds, `bounds exclusive`,
  `empty: pass`: the range is the passing band, so `V ≤ low` and `V ≥ high` are blocked, both inclusive. A zero impulse mean makes the ratio missing (the ratio already requires `right > right_floor`, floor 0).
  Both bounds are optional; the thresholds are held by the Research manifest, not by the Engine.
- **Volume source**: the base-bar `volume` of the market frame. The research reference uses `volume_value` from `market.sqlite3`;
  whether the two are the same series is checked at parity and reported.
- **Cost**: O(n) from prefix sums; a spec without a `leg_mean` operand pays nothing.

Not in this change: the vote, catalog and manifest bindings, research surfaces, deploy; V1.1, V1.2, V1.4.
