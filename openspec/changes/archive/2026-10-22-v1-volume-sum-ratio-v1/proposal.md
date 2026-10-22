## Why

Research metric **V1.1 "volume of the pullback against the volume of the impulse"** (group V of the almanac). It is the ratio of
the total volume traded in the pullback to the total volume traded in the impulse of the current wave.

It is a voter of **vote B** for EMA200 (BTC, ETH, SOL; owner's choice 2026-10-21): weight 0.66 at V1.1 ≤ 0.0574 and veto at
V1.1 ≤ 0.0441. Research on the working zones (unique entries BTC 447, ETH 372, SOL 218): 26 entries at ≤ 0.0574, 23 of them stops;
all 9 entries at ≤ 0.0441 are stops.

Meaning agreed with the owner on 2026-10-22: at this threshold V1.1 does not measure a "quiet" pullback. It catches **degenerate
waves**: an abnormally long impulse (280–835 bars against a usual 110–200) and/or a tiny pullback (1–16 bars against a usual ~80).
V1.1 is kept as a guard against such waves. The upper tail (pullback volume several times the impulse) was checked on EMA500
(2026-10-12) and EMA200 and does not work; it is not a reason for this change.

The Engine has the mean per bar (`leg_mean`, V1.3) but not the sum, so V1.1 cannot be built today.

## What Changes

Builds on `leg_mean` (V1.3): the same two legs, the same missing rules, the same `ratio`. No new indicator kind.

- **One new operand, `leg_sum`**: the sum of a base-bar field over one leg of the current touch of an episode.
  - Fields: `episode`, `leg` (`impulse` or `pullback`), `field` (only `volume`).
  - Impulse = bars `[S*, P]`, pullback = bars `[P+1, t]`, both ends inclusive, exactly as `leg_mean`. `t` is the evaluated bar.
  - Missing where there is no valid wave, where the leg is empty (`t = P` for the pullback) or a volume of the leg is not finite.
- **V1.1**: `ratio(leg_sum(pullback, volume), leg_sum(impulse, volume))`. A zero impulse sum makes the ratio missing (the ratio
  already requires `right > right_floor`, floor 0). It can be used in a `range` (`bounds exclusive`, `empty: pass`) or as a
  weighted vote input; levels, weights and veto come only from the strategy config.
- **Cost**: O(n) from the prefix sums `leg_mean` already builds; a spec without `leg_sum` pays nothing.

Not in this change: V1.2 and V1.4, the other vote B components, catalog and manifest bindings, Research surfaces, deploy.
