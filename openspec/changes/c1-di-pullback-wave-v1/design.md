## Context

- B2 (`b2-di-wave-v1`) gives `touch: previous` for `origin → peak`, `by_side` series, `value: from_start` and `ratio.right_floor`.
  C1 reuses all of them; the only new thing is where the previous wave ends.
- A1/A2 pullback is `peak → current`, both ends inclusive, only bars ≤ t read. `touches` rows carry `origin_bar`, `peak_bar` and
  `touch_bar` (`stack_episode.py`), so the previous pullback is fully known at the current touch.
- Research reference (owner's Mac, `c1/c1_values.py`; exports and parity files are produced on the owner's word) fixes the formulas.
  Where this design and the reference disagree, the reference wins and the difference is reported.

## Decisions

### D1. End point `touch`

`segment.to` MAY be `touch`: the `touch_bar` of the selected touch row. It is allowed only with `touch: previous` and
`from: peak`, so the wave is `P_{n−1} … T_{n−1}` inclusive. A current-touch segment keeps `peak → current`, whose end is the
evaluated bar. Any other use of `touch` as an end point is rejected at parse time. On the first touch of an episode the previous
segment is missing, as in B2.

No look-ahead: the previous touch bar is at or before the current touch's origin, so no bar after `t` is read.

### D2. Counter-trade series

`by_side` with `long = di_minus`, `short = di_plus`, both period 14 on the base timeframe (28 and 56 are parameters). The series is
not negated. The existing features are reused; DI warm-up and history follow B2 (D4a: DI over the whole loaded history, at least
about 400 bars before the earliest `P` it needs).

### D3. Values

`from_start` with `s = P`: `x[u] − x[P]` for `u = P … e`.

| metric | numerator (current) | denominator (previous) |
|---|---|---|
| C1.1 | `max(C[P_n … t]) − C[P_n]` | `max(C[P_{n−1} … T_{n−1}]) − C[P_{n−1}]` |
| C1.2 | `mean(C[P_n … t]) − C[P_n]` | `mean(C[P_{n−1} … T_{n−1}]) − C[P_{n−1}]` |

The current wave grows with `t`; at `t = P` it is 0 (one bar). The denominator is empty when the value is `≤ 1e-6` (zero,
negative or tiny, as in B2); a numerator `≤ 0` is a value.

### D4. Direction of the cut

Not an Engine decision. Bounds stay nullable and both tails are available; the manifest binds C1.1 low and C1.2 high as veto
sliders per the research result.

### D5. Cost

No new pass: the same prefix sums and sparse table as B2, the previous segment reads one more row. A spec without the `touch`
end point has the same node set and results as before.

### D6. Questions for the reference (before code)

Answered by the research thread's `c1_values.py` and its exports when the owner allows them:

1. The previous pullback ends on the touch bar of the previous row, inclusive.
2. The denominator floor 1e-6 holds for C1.1 and C1.2.
3. `C[P]` is the counter DI on the peak bar itself, the first bar of `P … t`.
4. The current pullback includes the evaluated bar `t`.
