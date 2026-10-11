## Context

- A1 (archived `a1-band-filter-v1`, Engine bb9f0bc) has the `segment` operand (aggregates `sum`, `mean_per_bar`; values
  `level`, `change`; `last_n` window; `negate`; side sign applied to the series first), the `ratio` operand and `range` with
  nullable bounds, `bounds`, `empty`. A segment is computed O(n) by prefix sums; the leg and its end points come from the
  current touch of the declared EMA-stack episode; only bars ≤ t are read.
- Research reference for A2 (owner's Mac, `a2_engine_ref_btc/eth.csv.gz`, scripts `a2_ideas_peek.py`, `a2_scan.py`) fixes the
  exact formulas. Where this design and the reference disagree, the reference wins and the difference is reported
  (the change is then limited to the decisions marked "reference").
- Research eligibility, same for all three branches: both legs at least 3 bars, and the impulse in its window moved away
  from the anchor (> 0); otherwise the value is missing and the bar is not blocked.

## Decisions

### D1. Reuse A1 blocks; add only what cannot be expressed

A2.1 is expressible today (ratio of two `last_n` segments). A2.2 needs the maximum of a k-bar change; A2.3 needs the sum of the
n largest absolute changes and the sum of absolute changes; the eligibility needs a condition on the other leg. These become
fields of the existing `segment`, not new operand kinds or a predicate class.

### D2. `value: change_over` with `span`

`span` is a positive integer, required exactly when `value` is `change_over`. The series is `D_k[u] = x[u] − x[u−k]`, with
`x` the series of `of` negated on the short side first. Over the window `s..e` it reads `D_k[u]` for `u = s..e`, hence
`x[s−k..e]`. The leg and window are those of A1: inclusive ends, `s = max(a, e − N + 1)` for `last_n`. Missing when any `x` read
is non-finite. A leg shorter than `span + 1` bars still reads bars before the leg (they exist in the series); only
non-finiteness makes it missing.

**Reference:** whether the research k-bar change may read before the window (`x[s−k]`) or starts at `s + k`. The text of the
task and A1's D2 convention say it reads before the window; the reference decides.

### D3. Aggregates

| aggregate | allowed `value` | result |
|---|---|---|
| `sum`, `mean_per_bar` | level, change, change_over | as in A1 |
| `max`, `min` | change, change_over | largest / smallest value over the window |
| `abs_sum` | change, change_over | sum of absolute values |
| `top_abs_sum` (+ `top`) | change, change_over | sum of the `top` largest absolute values; `top` a positive integer; `window.last_n` required |

`negate` multiplies the result by −1 after the aggregate (A2.2 numerator = −min of the k-bar change = max of the move toward
the anchor). All values count with their sign except in `abs_sum` / `top_abs_sum`. Fewer than `top` bars in the window: missing.

**Reference:** whether the absolute change counts every bar or only bars moving toward the anchor; the count rule for
`top_abs_sum` when the window has fewer than `top` bars. The reference decides; the parameters above are the proposal.

### D4. Cost

`sum` and `mean_per_bar` stay O(n) by prefix sums. New costs, stated so they can be checked:

- `max`, `min`: one table per (series, span) built once per evaluation, queried per bar in O(1) (sparse table, O(n log n)
  build) or a monotonic window; independent of leg length.
- `abs_sum`: prefix sums of `|Δ|`, O(n).
- `top_abs_sum`: bounded by `last_n`, so at most O(n · last_n) with a partial sort per bar, vectorized over bars; `last_n`
  is required so the cost cannot depend on leg length. A benchmark against the A1 band fixture is a task; the A1 batch speed
  (about 0.13 s per extra band candidate on the fixture) must not degrade for specs without the new fields.

### D5. Eligibility

`eligibility` is an optional object `{"legs_min_bars": N, "impulse_positive": bool}`, both keys optional, default no
condition, unknown keys rejected. It is evaluated on the current touch of the segment's episode, whatever leg the segment
itself reads:

- `legs_min_bars`: both `origin → peak` and `peak → current` must have at least `N` bars (`e − a + 1`, inclusive ends);
- `impulse_positive`: the impulse in its window moved away from the anchor, i.e. the mean per-bar change of `x` over the
  last `N_w` bars of `origin → peak` is greater than 0, where `N_w` is the segment's own `last_n` (the whole leg for a null window).

A segment that fails its eligibility is missing, so a ratio over it is missing and, with `empty: pass`, the bar is not
blocked. A2.1, A2.2 and A2.3 all carry `{"legs_min_bars": 3, "impulse_positive": true}`.

**Reference:** the exact "impulse moved away" statistic (mean change as above, or the impulse maximum used in A2.2) and
whether the bound is `> 0`. The reference decides.

### D6. Identity and memo

The segment identity carries `span`, `top` and `eligibility` only when set, so every A1 segment keeps its identity. Band
candidates differing only in the range bounds share the EMA columns, both segments and the ratio of each branch (as for A1);
the three branches share the `d` columns.

### D7. Live history

A segment with `change_over` reads `span` bars before the window start. The window start lies in the episode's own history
(`history_bars`); the planner adds the explicit entry of `span` extra bars so the series warm-up covers it.

### D8. Out of scope here

The "k of N" vote predicate, its trace and its parity (Step 2, a separate change after Step 1 is accepted). Catalog, manifest
bindings, the default grids and deploy wait for the owner's word.

## Alternatives not taken

- New operand kinds for A2.2 and A2.3: duplicate the segment geometry and windows.
- Eligibility as extra composite children: a missing value is needed so a ratio and a vote treat the bar as "no value"; a
  separate AND child would instead block or pass on its own.
- Unbounded `top_abs_sum` windows: cost would depend on leg length.
- A different anchor reference file: the anchor is a parameter of the series, covered by a unit test with another period.
