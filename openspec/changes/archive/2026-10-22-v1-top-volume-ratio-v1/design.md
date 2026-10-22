## Context

- Research reference: `altvals.py`, `top10(a, z)`: `x = VOL[a:z+1]; k = max(1, int(np.ceil(0.1 * len(x)))); mean of the k largest`;
  `v14 = top10(P+1, b) / top10(S, P)` when `b > P` and the impulse value is `> 0`.
- `ceil(0.1 · L)` is computed in float64 as in research; for share 0.1 it equals the integer ceiling for every L below 2000 (checked), e.g. L = 30 gives 3.

## Decisions

### D1. Operand `leg_top_mean`

`{"leg_top_mean": {"episode", "leg", "field", "share"}}`, all required. `field` is `volume`; `share` a finite number in (0, 1]. The
legs and missing rules are those of `leg_sum`. The value is the arithmetic mean of the `k` largest field values of the leg.

Rejected: an aggregate switch on `leg_sum`. A top mean has its own parameter (`share`) and its own cost; a separate operand keeps
`leg_sum` an O(n) prefix sum.

### D2. Computation

Impulse: one value per touch row (its `[S*, P]` does not depend on `t`), sorted once. Pullback: per touch, the bars of `[P+1, t]` are
kept sorted while `t` grows (one insertion per bar); a gap in the valid bars rebuilds the window. Cost O(n · L) in the worst case,
typically far less; measured on the full BTC history at parity.

### D3. V1.4

`ratio(leg_top_mean(pullback, volume, 0.1), leg_top_mean(impulse, volume, 0.1))`. No threshold is held by the Engine; vote B puts
`0.084 → veto` into its config.

### D4. Identity

Own node family `predicate.leg_top_mean` with params `leg`, `field`, `share`, upstream the episode and the market bars.
