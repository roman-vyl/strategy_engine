## Context

- Research: `review/ema100/feat100.py` with the 5m rule of `review/oi5/engine_rule/feat.py`: `W8p = at(p_bar)` of
  `OI / OI.rolling('30D').max()`, with at least 30 days of OI history at P. The 5m records are gapless, so 30 days = 8640 bars, and
  `rolling_max` with `min_periods = period` gives the same history condition.
- `touch_points(episode, size)` already returns `(valid, origin, peak)` of the current touch on every bar.

## Decisions

### D1. Operand `at_point`

`{"at_point": {"episode", "point", "operand"}}`, all three required, no other field. `point` is `peak` or `origin`. `operand` is
any operand of the layer except a constant and another `at_point`. Value on bar t: `inner[point(t)]` where the touch is valid,
missing otherwise or where `inner[point(t)]` is not finite. It is accepted wherever a ratio is accepted, and rejected as the operand
of a `change`.

Rejected: a `point` field on `ratio` or on features. Reading at a point is its own operation with its own node, and it composes
with any operand.

### D2. Identity

Own node family `predicate.at_point` with params `point` and the inner operand, upstream = the inner node and the episode. Its side
is always set (it reads the episode).

### D3. Parity reference

`W8p` from `review/oi5/engine_rule/feat_<coin>.npz` (full precision, Engine OI rule), 1e-9 relative, NaN equal, on all EMA200
entries of BTC, ETH and SOL.
