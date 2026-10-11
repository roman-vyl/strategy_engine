## Context

- A1 (archived `a1-band-filter-v1`, Engine bb9f0bc) has the `segment` operand (aggregates `sum`, `mean_per_bar`; values
  `level`, `change`; `last_n` window; `negate`; side sign applied to the series first), the `ratio` operand and `range` with
  nullable bounds, `bounds`, `empty`. A segment is computed O(n) by prefix sums; the leg and its end points come from the
  current touch of the declared EMA-stack episode; only bars ≤ t are read.
- Research reference for A2 (owner's Mac, `a2_ideas_peek.py` lines 10–20; the export `a2_engine_ref_btc/eth.csv.gz`, columns
  `bar,time_ms,side,s_bar,p_bar,accel,peak,conc`, comes from `a2_ideas_{coin}.npz`; the one-off exporting script is not in the
  treatise directory) fixes the exact formulas. Where this design and the reference disagree, the reference wins and the difference is reported
  (the change is then limited to the decisions marked "reference").
- Research eligibility, same for all three branches: both legs at least 3 bars, no non-finite change in the last 75 bars of
  either leg, and the sum of the impulse changes over its last 75 bars strictly greater than 0; otherwise the value is missing
  and the bar is not blocked.

## Decisions

### D1. Reuse A1 blocks; add only what cannot be expressed

A2.1 is expressible today (ratio of two `last_n` segments). A2.2 needs the maximum of a k-bar change; A2.3 needs the sum of the
n largest absolute changes and the sum of absolute changes; the eligibility needs a condition on the other leg. These become
fields of the existing `segment`, not new operand kinds or a predicate class.

### D2. `value: change_over` with `span`

`span` is a positive integer, required exactly when `value` is `change_over`. With `x` the series of `of` negated on the short
side first, the values over the window `s..e` are `D[u] = x[u] − x[u−span]` for `u = s+span−1..e`: every `span`-bar change
made of `span` one-bar changes that all lie in the window. The earliest value reads `x[s−1]`, the bar before the window,
exactly as the one-bar `change` of A1 does, and nothing earlier. A window with fewer than `span` bars gives no value. Missing
when any `x` read is non-finite.

*Confirmed against the reference* (`a2_ideas_peek.py` line 15): the research takes the rolling sum of 3 consecutive per-bar
changes inside the trimmed 75-bar window (`np.convolve(..., "valid")`); bars before the window or the leg do not enter beyond `x[s−1]`.

### D3. Aggregates

| aggregate | allowed `value` | result |
|---|---|---|
| `sum`, `mean_per_bar` | level, change, change_over | as in A1 |
| `max`, `min` | change, change_over | largest / smallest value over the window |
| `abs_sum` | change, change_over | sum of absolute values of all bars of the window |
| `top_abs_sum` (+ `top`) | change, change_over | sum of the `top` largest absolute values; `top` a positive integer; `window.last_n` required |

`negate` multiplies the result by −1 after the aggregate (A2.2 numerator = −min of the 3-bar change = the strongest move toward
the anchor). `max`/`min` keep their sign. `abs_sum` and `top_abs_sum` count every bar of the window, toward or away from the
anchor; with fewer than `top` values `top_abs_sum` is the sum of all of them, so A2.3 is exactly 1 on a 3–4 bar window.

*Confirmed against the reference* (line 19): `np.sort(abs(dr))[-5:].sum() / abs(dr).sum()` over all bars of the trimmed window; a sum of 0 gives no value.

### D4. Cost

`sum`, `mean_per_bar` and `abs_sum` stay O(n) by prefix sums. New costs, stated so they can be checked:

- `max`, `min`: one table per (series, span) built once per evaluation, queried per bar in O(1) (sparse table, O(n log n)
  build) or a monotonic window; independent of leg length.
- `top_abs_sum`: bounded by `last_n`, so at most O(n · last_n) with a partial sort per bar, vectorized over bars; `last_n`
  is required so the cost cannot depend on leg length. A benchmark against the A1 band fixture is a task; the A1 batch speed
  (about 0.13 s per extra band candidate on the fixture) must not degrade for specs without the new fields.

### D5. Eligibility

`eligibility` is an optional object `{"legs_min_bars": N, "window": W, "impulse_positive": bool}`, all keys optional,
`impulse_positive` requiring `window`, unknown keys rejected. It is evaluated on the current touch of the segment's episode
whatever leg the segment itself reads, and its window `W` is independent of the segment's own `window`:

- `legs_min_bars`: both `origin → peak` and `peak → current` have at least `N` bars (inclusive ends, counted on the whole
  legs before any window);
- `window`: every one-bar change in the last `W` bars of the impulse and of the pullback is finite;
- `impulse_positive`: the sum of the one-bar changes of the last `W` bars of the impulse is strictly greater than 0.

A segment that fails its eligibility is missing, so a ratio over it is missing and, with `empty: pass`, the bar is not blocked.
A2.1, A2.2 and A2.3 all carry `{"legs_min_bars": 3, "window": 75, "impulse_positive": true}`, so they share one eligibility
even though A2.1 reads 12 and 75 bars of the pullback.

*Confirmed against the reference* (lines 12–14): legs `len < 3` → no value, counted on the whole legs before the trim to 75;
`np.isnan(di).any() or np.isnan(dr).any() or di.sum() <= 0` on the trimmed windows → no value for all branches.

*To confirm at parity*: that the research leg windows (`MT.window`, `book_metrics_v6/metrics.py`) are inclusive at both ends,
so `len(I) = P − S* + 1` and `len(R) = t − P + 1`; the situation labels and block counts of the export test it.

### D5a. Division

A ratio is missing when its denominator is ≤ 0 or non-finite (A1 requirement "Ratio operand"), which matches the reference
(`nr > 0`, `pi > 0`). A numerator ≤ 0 is a valid value: it gives a value ≤ 0 and the bar is not blocked by a high cut.

### D6. Identity and memo

The segment identity carries `span`, `top` and `eligibility` only when set, so every A1 segment keeps its identity. Band
candidates differing only in the range bounds share the EMA columns, both segments and the ratio of each branch (as for A1);
the three branches share the `d` columns.

### D7. Live history

The new fields read at most one bar before the window start, like the one-bar `change` of A1, and the window lies in the
episode's own history (`history_bars`). A predicate over such a segment therefore contributes the zero-additional entry of A1;
no new planner rule is needed.

### D8. Out of scope here

The "k of N" vote predicate, its trace and its parity (Step 2, a separate change after Step 1 is accepted). Catalog, manifest
bindings, the default grids and deploy wait for the owner's word.

## Alternatives not taken

- New operand kinds for A2.2 and A2.3: duplicate the segment geometry and windows.
- Eligibility as extra composite children: a missing value is needed so a ratio and a vote treat the bar as "no value"; a
  separate AND child would instead block or pass on its own.
- Unbounded `top_abs_sum` windows: cost would depend on leg length.
- A different anchor reference file: the anchor is a parameter of the series, covered by a unit test with another period.
