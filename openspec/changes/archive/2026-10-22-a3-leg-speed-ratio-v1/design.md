## Context

- Research reference: `altvals.py`: `Hs = |Pp − Sp|`, `nI = P − S + 1`, `nR = b − P + 1`, `dR = |Pp − C[b]|`; when `Hs > 0`:
  `a3 = (dR / nR) / (Hs / nI)`.
- `origin_price`, `peak_price` are the touch-table prices used by A1, B1, C3.1 and C5.

## Decisions

### D1. Operand `leg_speed`

`{"leg_speed": {"episode", "leg"}}`, both required, `leg` in `impulse` | `pullback`. Distances are absolute, so the short side needs
no sign. The impulse value does not depend on `t`; the pullback value reads the close of `t` only.

Rejected: one fixed `speed_ratio` operand. Two leg speeds composed by the existing `ratio` keep each operand atomic, mirror
`leg_sum` / `leg_top_mean`, and let research try other combinations from config.

### D2. Missing cases

Missing where the touch has no valid wave (`S* ≤ P ≤ t` as for the other leg operands) or an input price is not finite. A zero
impulse height gives an impulse speed of 0, and the ratio's default `right_floor` 0 makes A3 missing, as research's `Hs > 0`.

### D3. Identity

Own node family `predicate.leg_speed` with param `leg`, upstream the episode and the market bars.
