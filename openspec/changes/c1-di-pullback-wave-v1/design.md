## Context

- B2 (`b2-di-wave-v1`) gives `touch: previous` for `origin → peak`, `by_side` series, `value: from_start` and `ratio.right_floor`.
  C1 reuses all of them; the only new thing is where the previous wave ends.
- A1/A2 pullback is `peak → current`, both ends inclusive, only bars ≤ t read. `touches` rows carry `origin_bar`, `peak_bar` and
  `touch_bar` (`stack_episode.py`), so the previous pullback is fully known at the current touch.
- Research reference (owner's Mac, `c1/c1_values.py`; exports and parity files are produced on the owner's word) fixes the formulas.
  Where this design and the reference disagree, the reference wins and the difference is reported.

## Decisions

### D1. End point `next_origin`

`segment.to` MAY be `next_origin`: the `origin_bar` (S*, the true low or high that starts the wave) of the CURRENT touch row. It is
allowed only with `touch: previous` and `from: peak`, so the previous pullback is `P_{n−1} … S*_n` inclusive: it runs to the real
extreme of the finished pullback, not to the bar where it first touched the EMA (owner 2026-10-12: after the touch the low went
further on 69 % of BTC EMA500 cases, median 4 bars). The CURRENT wave ends at `touch`: the `touch_bar` of the current touch row (`peak → touch`, `touch: current`, owner 2026-10-12: "до касания", the entry is decided on the touch/trigger bar). The current touch row exists only from its touch bar on, so `touch_bar ≤ t` always and the value stays fixed on the bars after the touch. Any other use of `next_origin` is rejected at parse time. The segment is missing on the
first touch of an episode and when `S*_n` is not after `P_{n−1}` (degenerate), and the segment is empty then, as in B2.

No look-ahead: `S*_n` is at or before the current touch bar and so at or before `t`; no bar after `t` is read.

### D2. Counter-trade series

`by_side` with `long = di_minus`, `short = di_plus`, both period 14 on the base timeframe (28 and 56 are parameters). The series is
not negated. The existing features are reused; DI warm-up and history follow B2 (D4a: DI over the whole loaded history, at least
about 400 bars before the earliest `P` it needs).

### D3. Values

`from_start` with `s = P`: `x[u] − x[P]` for `u = P … e`.

| metric | numerator (current) | denominator (previous) |
|---|---|---|
| C1.1 | `max(C[P_n … T_n]) − C[P_n]` | `max(C[P_{n−1} … T_{n−1}]) − C[P_{n−1}]` |
| C1.2 | `mean(C[P_n … T_n]) − C[P_n]` | `mean(C[P_{n−1} … T_{n−1}]) − C[P_{n−1}]` |

The current wave `P_n … T_n` ends at the touch bar of the current touch (T_n); it can be 0 (one bar). The denominator is empty when the value is `≤ 1e-6` (zero,
negative or tiny, as in B2); a numerator `≤ 0` is a value.

### D4. Direction of the cut

Not an Engine decision. Bounds stay nullable and both tails are available; the manifest binds C1.1 low and C1.2 high as veto
sliders per the research result.

### D5. Cost

No new pass: the same prefix sums and sparse table as B2, the previous segment reads one more row. A spec without the `next_origin`
end point has the same node set and results as before.

### D6. Questions for the reference (before code)

Answered by the research thread's `c1_values.py` and its exports when the owner allows them:

1. The previous pullback ends on the origin bar (S*) of the current touch row, inclusive (owner 2026-10-12; the earlier touch-bar end is dropped).
2. The denominator floor 1e-6 holds for C1.1 and C1.2.
3. `C[P]` is the counter DI on the peak bar itself, the first bar of `P … T`.
4. The current pullback ends at the touch bar of the current touch, inclusive (owner 2026-10-12: "до касания"; the earlier `P … t` is dropped).
