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
long and `force_against` on short, and `−1` otherwise. Bar 0, the first bar of the data window, has force 0 (the reference convention). A non-finite close or
volume makes the bar non-finite and the leg missing. If the Engine's first bar differs from the research window the parity report
states how. The series is built from the shared market arrays (`close`, `volume`) per side and
cached with the node, not per candidate.

### D3. V2.2

`range(ratio(leg_mean(pullback, force_against), leg_mean(impulse, force_with)))`, `bounds exclusive`, `empty: pass`: value
`pb / imp` with `pb` the mean of `−f` over the pullback and `imp` the mean of `f` over the impulse. `imp ≤ 0` makes the ratio missing
and the entry passes. `pb ≤ 0` stays a value. Defaults are all off; the preset high (candidate 10) lives in the Research manifest.

### D4. Mean over all candles

Both means average the signed force over every candle of the leg (net force per candle), not only over candles whose force points in the
named direction. Confirmed by the Mac task (mean of the signed force over all bars: `g × Σ force ÷ bars` for the impulse, `−g × Σ force ÷ bars` for the pullback); a difference found at parity is reported before any change.

### D5. First impulse bar

For `u = S*` the force reads `close[S*−1]`, the bar before the origin. Confirmed by the Mac task (`force[t] = (close[t] − close[t−1]) × volume[t]` for every bar). When `S* = 0` the force of that bar is 0.

### D6. Identity and cost

Same node family and params as V1.3, with the new field names. Candidates that differ only in a bound share both operands and the
ratio. O(n) per series per side. No lookahead: the value on `t` reads bars `≤ t` only.

### D7. Trace

The leg mean operand also yields, for parity and the trace, the signed force sum and the bar count of each leg (sum = mean × count);
`mean_imp`, `mean_pb` and V2.2 are the operand values.
