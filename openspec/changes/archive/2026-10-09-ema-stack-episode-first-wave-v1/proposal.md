## Why

Wave 1 of an EMA stack episode runs from the episode start bar. Its origin `S*_1` is the lowest low since that bar (long). When the pullback to touch 1 makes a lower low than every bar since the start, the running origin moves to the pullback bar, the peak resets to the same bar, and the up leg `S* → P` collapses to one bar.

Example (`ema_pullback:163782b777c0c4d8cd38c79c`, BTC long, trade 6): the stack forms on 2026-07-14 20:55, the pullback to touch 1 on 2026-07-16 makes the lowest low since the start, and `S*` and `P` land on the same 5m bar.

The start bar of an episode is where the stack order forms, not where the move began. The wave that ends at touch 1 began earlier, at the last time price was at the anchor before the stack formed.

## What Changes

- The origin of wave 1 takes the lower of two candidates (long; the higher for short):
  - the running lowest low since the episode start bar, as today;
  - the low of the nearest bar to the left of the start bar whose range covers the anchor (`low ≤ anchor ≤ high`), searched back without a bound to the first such bar.
- The peak `P_1` is the highest high from the chosen origin to the bar before touch 1. It may lie left of the start bar.
- If no contact bar exists left of the start bar, wave 1 is unchanged.
- A gap or a run of bars wholly above or below the anchor is not a candidate.
- Waves `k > 1`, zones, false breaks, touch numbering, stack breaks, censoring and causality are unchanged.

## Impact

- Wave 1 geometry changes for episodes whose nearest left contact has a lower low than the running minimum. The origin of wave 1 and the data derived from it (up leg 1 and down leg 1 ranges, `episode` operand reads on the first leg) may now lie left of the episode start.
- The history route returns the same shapes; the origin `time_ms` of wave 1 may precede `start_ms` of its episode.
- The cost of the projection does not grow: the nearest left contact is read from one vectorized pass over the bars.
- The episode node version is unchanged. No consumer released wave 1 geometry before this change.
