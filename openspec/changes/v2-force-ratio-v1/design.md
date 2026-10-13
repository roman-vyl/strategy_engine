## Context

- V1.3 (`leg_means.py`, operand `leg_mean`) already averages a base-bar series over `[S*, P]` and `[P+1, t]` from prefix sums and
  treats a non-finite bar in the leg as missing.
- Research reference: `v2/v2_engine_ref.py` (Mac); reference rows carry imp, n_imp, pb, n_pb, v2_2. Where this change and the
  reference differ, the reference wins (task rule).

## Decisions

### D1. Fields instead of a new operand

`field` of `leg_mean` gains `force_with` and `force_against`. The mean, the legs, the missing rules and the node family
`predicate.leg_mean` stay as in V1.3, and so does the identity (the field is already in it). Rejected: a separate `leg_force`
operand, because it would duplicate the leg and prefix-sum logic for one differing input series.

### D2. The derived series

For the evaluated side the series is `sign × (close[u] − close[u−1]) × volume[u]` for `u ≥ 1`, with `sign = +1` for `force_with` on
long and `force_against` on short, and `−1` otherwise. Bar 0 has no previous close and is missing. A non-finite close or volume
makes the bar non-finite and the leg missing. The series is built from the shared market arrays (`close`, `volume`) per side and
cached with the node, not per candidate.

### D3. V2.2

`range(ratio(leg_mean(pullback, force_against), leg_mean(impulse, force_with)))`, `bounds exclusive`, `empty: pass`: value
`pb / imp` with `pb` the mean of `−f` over the pullback and `imp` the mean of `f` over the impulse. `imp ≤ 0` makes the ratio missing
and the entry passes. `pb ≤ 0` stays a value. Defaults are all off; the preset high (candidate 10) lives in the Research manifest.

### D4. Mean over all candles

Both means average the signed force over every candle of the leg (net force per candle), not only over candles whose force points in the
named direction. This is the task text; the Mac confirms it when exporting the reference, and a difference found at parity is
reported before any change.

### D5. First impulse bar

For `u = S*` the force reads `close[S*−1]`, the bar before the origin. When `S* = 0` the bar is missing and so is the impulse mean.
Confirmed against the reference at parity.

### D6. Identity and cost

Same node family and params as V1.3, with the new field names. Candidates that differ only in a bound share both operands and the
ratio. O(n) per series per side. No lookahead: the value on `t` reads bars `≤ t` only.
