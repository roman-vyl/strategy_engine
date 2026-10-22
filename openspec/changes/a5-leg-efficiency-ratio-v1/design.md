## Context

- Research reference: `btc_recheck/code/altvals.py` `er(a, z)` and `a5 = er(P, b) − er(S, P)` when `b > P`; the ratio form
  `review/a5ex/ratio_grid.py`: `eR / ei` where `ei > 0`. `er` is missing when `z ≤ a` or the path length is 0.

## Decisions

### D1. Operand `leg_efficiency`

`{"leg_efficiency": {"episode", "leg"}}`, both required, `leg` in `impulse` | `pullback`. Value `|close[z] − close[a]| / (cad[z] −
cad[a])` with `cad` the prefix sum of `|close[k] − close[k−1]|`; impulse `a = S*, z = P`, pullback `a = P, z = t`. Missing when
`z ≤ a`, the path is 0, or a close of `[a, z]` is not finite (a prefix count of non-finite closes gates it). Only closes up to `t`.

Rejected: a fixed `a5` operand with the ratio inside. Two leg values composed by `ratio` keep the operand atomic, like `leg_speed`.

### D2. Identity

Own node family `predicate.leg_efficiency` with param `leg`, upstream the episode.
