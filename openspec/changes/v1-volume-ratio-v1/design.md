## Context

- `touches` rows of the episode carry `origin_bar` (S*) and `peak_bar` (P); the leg points of the current touch are known at `t`
  (`candles.touch_points`). B1 already fixed that the pullback starts at `P+1`.
- Research reference: `v1/v1_engine_ref.py` (Mac); reference rows carry vol_sum and bar count of both legs, mean_imp, mean_pb, v1_3.

## Decisions

### D1. Operand `leg_mean`

`{"leg_mean": {"episode", "leg", "field"}}`. `episode` is a declared episode, `leg` impulse or pullback, `field` is `volume`.
Impulse `[S*, P]`, pullback `[P+1, t]`. Value = `sum(field[begin..end]) / (end − begin + 1)` from prefix sums. Missing when the
touch point is not valid, the leg is empty (`P+1 > t`) or a bar of the leg has a non-finite field.

### D2. V1.3

`range(ratio(leg_mean(pullback), leg_mean(impulse)))` with `bounds exclusive` and `empty: pass`: the range is the passing band, so the entry is blocked when `V ≤ low` or `V ≥ high`, both inclusive.
Impulse mean 0: `right > 0` is false, the ratio is missing, the entry passes. Defaults are all off; the preset low 0.23 lives in
the Research manifest.

### D3. Identity and cost

The operand is its own node family `predicate.leg_mean` with params leg and field, upstream the episode and the market bars. Labels
are not part of it. Candidates that differ only in a bound share the two operands and the ratio. O(n) per series.

### D4. Volume source

The Engine reads `MarketBar.volume` of the base series. If it differs from research `volume_value` the parity report states how.
