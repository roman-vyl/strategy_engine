## Why

Research metric **V2.2 "mean Elder force per candle of the pullback against the impulse"** (group V of the almanac, card V2).
Elder's force of a candle is the price change times the volume. Of the three variants (V2.1 sums, V2.2 means per candle, V2.3 peak
EMA13) only V2.2 gave a consistent picture on BTC, ETH and EMA1000: its upper tail (a pullback pushing against the trade much
harder per candle than the impulse pushed for it) has more stop-losses than the base everywhere. Research candidate, not canon:
block V2.2 ≥ 10; below about 5 it hurts. On BTC EMA500 W7 / LB 20 / SL 7 / TP 5.5 it removes only a few trades directly.

The owner asked for V2.2 as an Engine component on 2026-10-13, on the same two legs as A1/A2/B1/V1.3. The task is
`engine-tasks/v2/v2_engine_task.md`. The component is atomic: one value with an optional low and an optional high bound. It knows
nothing about veto, "k of n" or weights; those roles belong to the future voting module.

## What Changes

Builds on the V1.3 `leg_mean` operand, `ratio` and `range` with nullable bounds. No new operand, no new indicator kind.

- **Two new `leg_mean` fields, `force_with` and `force_against`**: the mean over a leg of the side-signed candle force.
  - Candle force `F[u] = (close[u] − close[u−1]) × volume[u]` on the base bars.
  - `force_with` is `F[u]` on the long side and `−F[u]` on the short side (positive = with the trade); `force_against` is its negation.
  - The legs are those of V1.3: impulse `[S*, P]`, pullback `[P+1, t]`, both ends inclusive. The first impulse bar reads `close[S*−1]`.
- **V2.2 as a block**: `ratio(leg_mean(pullback, force_against), leg_mean(impulse, force_with))` in a `range` with nullable bounds,
  `bounds exclusive`, `empty: pass`; blocked when `V2.2 ≤ low` or `V2.2 ≥ high`, both inclusive. A non-positive impulse force makes
  the ratio missing (the ratio already requires `right > right_floor`, floor 0) and the entry passes. A negative pullback force is a
  value (the pullback did not push against the trade), not an empty one.
- **Cost**: O(n) from prefix sums; the derived series is built once per side and only for specs that use a force field. A spec
  without a force field pays nothing and keeps every identity.

Thresholds (low, high) are held by the Research manifest, not by the Engine. Not in this change: the vote, veto roles, catalog and
manifest bindings, research surfaces, deploy; V2.1 and V2.3.
