## Context

- Research reference (`review/oi5/engine_rule/feat.py` over `review/ema100/feat100.py`): `oi(x)` is the Bybit 5min OI record with
  `ts <= open(x)`; `O1 = 100 * (oi(P) / oi(S*) - 1)`, defined where both OI values and the entry OI exist.
- Engine: `open_interest` is an optional base-bar market field (SE #47, #48); a bar without a record has NaN, never an earlier value.
- Wave points come from `touch_points` (current touch) and the previous touch row (as `pullback_depth` with `touch: previous`).

## Decisions

### D1. Operand `leg_change`

`{"leg_change": {"episode", "leg", "field", "touch"?}}`; `episode`, `leg`, `field` required. Value on bar `t`:
`100 * (x[end] / x[begin] - 1)` with `(begin, end)` = `(S*, P)` for `impulse`, `(P, t)` for `pullback`, `(S*₀, P₀)` for `impulse`
with `touch: previous`. Missing where there is no valid wave (or no previous touch), either value is not finite, or `x[begin] <= 0`.
Bars after `t` are not read. Not signed by side: the sign of the change is the market's, as in research.

Rejected: an `oi_change` operand bound to OI. The same operand gives the price change of a leg (needed later by kI, W1) and
keeps the family atomic, like `leg_mean`.

### D2. Identity

Own node family `predicate.leg_change` with params `leg`, `field`, `touch`; upstream the episode.

### D3. Known difference from research

Research requires the entry OI to exist as well for O1; the operand reads only `S*` and `P`. Where the entry bar has no OI the
operand still gives a value. Parity reports the count of such entries.
