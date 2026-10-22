## Context

- Research reference: `altvals.py` lines for C3.2:
  `P0, Pp0, Sp0 = prev_p_bar, prev_p_price, prev_s_price`; when `S > P0`:
  `ext0 = L[P0:S+1].min()` (long) or `H[P0:S+1].max()`, `H0 = |Pp0 − Sp0|`; when `H0 > 0` and `Hs > 0`:
  `v0 = g · (Pp0 − ext0) / H0`, and when `v0 > 1e-6`: `c32 = c31 / v0`.
- The previous wave is the previous touch row of the same episode, as the segment operand's `touch: previous` already reads it
  (`peak` to `next_origin`, the current origin bar).

## Decisions

### D1. `touch` on `pullback_depth`

`{"pullback_depth": {"episode", "touch"?}}`, `touch` in `current` | `previous`, default `current`. With `previous` the value is
the depth share of the previous pullback measured over `[P0, S*]`, both ends inclusive, on every bar whose current touch is valid
and has a previous row in the same episode. It does not change with `t`; only bars `≤ S* ≤ t` are read.

Rejected: a dedicated `previous_depth` operand. The formula is the same; one operand with a `touch` field mirrors `segment`.

### D2. C3.2 as a ratio

`ratio(pullback_depth, pullback_depth touch previous, right_floor 1e-6)`. The existing ratio makes the value missing when the
right side is `≤ right_floor`, which is research's `v0 > 1e-6`; a missing C3.1 (`Hs = 0`) makes it missing too.

### D3. Computation and identity

Previous: one value per touch row, computed once and spread to the bars of that touch. Node family `predicate.pullback_depth`;
params `{}` for `current` (unchanged identity) and `{"touch": "previous"}` for `previous`.
