## Why

Vote W8 variant 8 for EMA200 has two voters on **vol1h**: the volume of the last hour against the mean hourly volume of the 20 days
before it (research `review/live/reclaim/sim.py` `vol1h_bars`, same as `ema100/mac/code/altvals.py`):

`vol1h[i] = sum(V[i−11..i]) / (sum(V[i−5771..i−12]) / 480)`, missing where the denominator is ≤ 0 or the history is shorter.

Without it, variant 8 loses on every working zone (review thread, BTC 12.0k vs 14.4k, SOL W6 21.8k vs 32.3k). The owner asked on
2026-10-27 (15:47) for a universal tool rather than one tied to a particular volume: the volume series is an argument of the spec,
so that a later volume of the main coin (spot or another series) is a config change only. Agreed 15:49 («Da»).

## What Changes

- **New feature kind `rolling_sum {source, period, lag}`**. It is the sum of a base-bar field over `period` candles ending `lag`
  candles before the current one (`lag` 0 = the current one included).
  - `source` is any field the Engine carries on a bar: `open`, `high`, `low`, `close`, `volume`, `open_interest`. A field added
    later, such as a spot volume, becomes a source with no other change.
  - The value is missing until the window holds `period` finite values.
- **vol1h** is a config composition, and the Engine holds no number:
  `ratio(rolling_sum(volume, 12), ratio(rolling_sum(volume, 5760, lag 12), const 480))`.
  A non-positive denominator gives a missing value (the ratio rule).
- **Cost**: one vectorised rolling sum per distinct request, shared like other features.

Not in this change: a new volume series (spot) as a bar field. That is MDS and Engine market-data work once the owner loads it.
Also out of scope: the vote voters (`vol1h` low/high are vote config) and deploy.
