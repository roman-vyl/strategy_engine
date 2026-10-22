## Context

- Research reference: `altvals.py`: `nI = P − S + 1`, `nR = b − P + 1`; when `Hs > 0`: `a4 = nR / nI`.
- `Hs = |Pp − Sp| > 0` holds for every wave the episode builds (the peak is strictly beyond the origin); parity checks it.

## Decisions

### D1. Operand `leg_bars`

`{"leg_bars": {"episode", "leg"}}`, both required, `leg` in `impulse` | `pullback`. Integer counts as float64. The impulse count does
not depend on `t`; the pullback count is `t − P + 1`. No price is read.

Rejected: a fixed `duration_ratio` operand. Two leg counts composed by the existing `ratio` keep the operand atomic, like `leg_speed`.

### D2. Identity

Own node family `predicate.leg_bars` with param `leg`, upstream the episode.
