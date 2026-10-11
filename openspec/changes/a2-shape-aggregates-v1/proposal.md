## Why

A1 measures the mean speed of the pullback relative to the impulse. A mean cannot see the shape of a leg. Research found three
shape metrics on the same per-bar change of `d = EMA(close, 5) − anchor EMA` whose rank correlation with A1 is only 0.4–0.5
and that cut a different kind of bad entry each:

- **A2.1 acceleration into the touch**: pullback speed over the last 12 bars ÷ over the last 75 bars.
- **A2.2 peak hit**: strongest 3-bar move toward the anchor on the pullback ÷ strongest 3-bar move away from it on the impulse.
- **A2.3 concentration**: share of the 5 largest bar changes in the pullback's total absolute change.

The owner wants each as its own Engine component first (Step 1, this change), each with a wide parity against the research
reference. The "k of N" vote over them is Step 2 and a separate change, built only after Step 1 is accepted.

## What Changes

Everything builds on the A1 blocks (`segment`, `ratio`, `range`, archived as `a1-band-filter-v1`); no new indicator kind and no
new predicate class.

- **A2.1 needs no new block**: `ratio(segment(Δd, peak→current, change, last_n 12, mean_per_bar, negate), segment(Δd,
  peak→current, change, last_n 75, mean_per_bar, negate))`, parameters 12 and 75 live in the spec.
- **Segment value `change_over`** with `span` k: the k-bar change `x[u] − x[u−k]` per bar (A2.2 uses k = 3). `change` stays the
  1-bar change.
- **Segment aggregates** added to `sum` and `mean_per_bar`:
  - `max`, `min`: the largest / smallest value of the series over the window (A2.2: `change_over` span 3);
  - `abs_sum`: the sum of absolute values (A2.3);
  - `top_abs_sum` with `top` n: the sum of the n largest absolute values (A2.3, n = 5). It needs a bounded
    `window.last_n`.
- **Segment eligibility** (new optional field): `{"legs_min_bars": N, "impulse_positive": bool}`. The segment is missing unless
  both legs of the current touch have at least N bars and, when asked, the impulse moved away from the anchor. Research uses
  N = 3 and the impulse condition for all three branches, and no existing block can express a condition on the other leg.
- **Costs**: `max`/`min` and `top_abs_sum` are not prefix sums. Their cost is stated and benchmarked (design D4) so the batch
  speed of A1 is not degraded.

A2.2 and A2.3 as blocks:

```
A2.2 = ratio( segment(d, peak→current, change_over 3, last_n 75, min, negate, eligibility),
              segment(d, origin→peak,  change_over 3, last_n 75, max,         eligibility) )
A2.3 = ratio( segment(d, peak→current, change, last_n 75, top_abs_sum 5, eligibility),
              segment(d, peak→current, change, last_n 75, abs_sum,       eligibility) )
```

each inside a `range` with nullable bounds (`bounds exclusive`, `empty pass`) as in A1. Defaults of the grids live in the
Research manifest, not in the Engine, as decided for A1.

Nothing changes for specs that use none of the new fields.

## Impact

- `pre-entry-predicates-v1`: MODIFIED `Segment operand shape`, `Segment aggregation fields`, `Segment value`; ADDED
  `Segment k-bar change`, `Segment extremum aggregates`, `Segment absolute-change aggregates`, `Segment eligibility shape`, `Segment eligibility leg length`, `Segment eligibility impulse direction`.
- `batch-computation-reuse`: MODIFIED `Identity twins for predicates and composites`; ADDED
  `Segment aggregate cost`.
- `live-calculation-window-planning`: ADDED `History policy for k-bar segment values`.
- Not modified: `ema-stack-episode-v1`, `ema-pullback-composite-setup-v1` (the existing operand value trace already covers a
  range over a segment or ratio), the feature-kind contract, the composer catalog.
- Code: `strategies/ema_pullback/predicates.py` (parse, evaluation, identity); the same files as A1 for nothing else.

## Verification

Step 1 ends with a parity report and a stop for the owner's review, case × branch: rows compared, max |diff|, NaN
mismatches, block-count differences, full-run differences (see tasks).

- Unit tests: every new field against a brute-force loop; windows shorter than `span`, `top` and the legs; ties; zero and
  negative denominators; NaN inside the window; later touches; short side; a different anchor period (no EMA1000 reference
  needed); old segments and ranges unchanged.
- Reference: `a2_engine_ref_btc.csv.gz` (2185 entries) and `a2_engine_ref_eth.csv.gz` (1970) on the owner's Mac, with a
  situation label per entry; situations without a real entry use synthetic series computed by the same reference code.
- Full runs: standard research-service batch run against the deployed Engine, compared with the replay row, like the A1
  control cells.
- Gate: ruff, mypy, the full suite without `tests/parity`, `openspec validate a2-shape-aggregates-v1 --strict`.
