## Context

- A1/A2 (`a1-band-filter-v1`, `a2-shape-aggregates-v1`, Engine e00defc) give `segment`, `ratio` and `range` over the legs of the
  current touch of a declared EMA-stack episode: touch row `first_row[episode_id] + touch_number − 1`, origin `S*`, peak `P`, both
  ends inclusive, only bars ≤ t read, the series side-signed (negated on the short side).
- `di_plus` and `di_minus` are Wilder RMA features (`adx_dmi.py`, BBB-compatible), period 14 by default, any timeframe; B2 uses the
  base timeframe.
- Research reference (owner's Mac, `book_metrics_v6/b2/`, exported for BTC and ETH: `b2/b2_engine_ref_{btc,eth}.csv.gz`,
  `b2/b2_parity_{btc,eth}.json`) fixes the exact formulas. Where this design and the reference disagree, the reference wins and
  the difference is reported; the decisions marked "reference" are the ones it may overrule.

## Decisions

### D1. Previous touch: a `touch` field on the segment (not a new operand)

`segment.touch` is `current` (default) or `previous`. The points of the segment are read from row `r` for `current` and `r − 1`
for `previous`, where `r = first_row[episode_id] + touch_number − 1`. `previous` requires `touch_number ≥ 2`; on the first touch of
an episode the segment is missing, so the ratio is missing and `empty: pass` lets the entry through. Only the same episode counts.
Whether research takes wave n−1 from an earlier episode is a reference question (D7); the default here is the same episode only.

`previous` is allowed with `from`/`to` of `origin → peak` only (the previous touch's pullback and `current` end have no meaning
for B2); other pairs with `previous` are rejected. For `previous`, `current` as an end point is rejected.

No look-ahead: both touch rows are at or before the current touch and the impulse of each ends at its own peak, which is not
after `t`; no bar after `t` is read.

### D2. Trade-side series: `by_side`

`of` accepts `{"by_side": {"long": <feature>, "short": <feature>}}` next to a single feature and a difference. The evaluated
side picks its feature. A `by_side` series is **not** negated on the short side (a single feature or difference still is, as in
A1/A2); `segment.negate` keeps its meaning. B2: `long = di_plus`, `short = di_minus`, both of period 14 on the base timeframe.
Both features enter the feature plan whichever side is evaluated (the planner already collects the features of a predicate).
Identity: the series enters the segment identity as `by_side` with both feature identities, so a `by_side` segment never shares a
node with a plain-feature segment.

### D3. Value `from_start`

`from_start` reads `v[u] = x[u] − x[s]` for `u = s … e`, `s` the first bar of the window (the leg start `S*` when `window` is null,
as in B2). `sum`, `mean_per_bar`, `max` and `min` aggregate it:

| aggregate | value of `from_start` over `s … e` |
|---|---|
| `max` | `max(x[s … e]) − x[s]` |
| `min` | `min(x[s … e]) − x[s]` |
| `sum` | `Σ x[s … e] − (e − s + 1) · x[s]` |
| `mean_per_bar` | `mean(x[s … e]) − x[s]` |

`x[s]` itself contributes 0 to the window. `change` and `change_over` aggregates (`abs_sum`, `top_abs_*`) are not allowed with
`from_start`. A non-finite `x` anywhere in `s … e` makes the value missing (DI warm-up). A window of one bar gives 0.

B2.1 uses `max`, which is `max(D) − D[S*]` (the rise to the peak); B2.2 uses `mean_per_bar`, which equals
`mean(D over the leg) − D[S*]` (the average area with the duration removed). `mean_per_bar` is the same prefix sum as A1 minus
the start level; `max`/`min` reuse the A2 sparse table on the level series.

Alternative considered: a `first` aggregate (the level at the window start) and building "max − first" with a difference of two
segments. It needs two segments per wave, a difference operand, and it would not share the sparse table; rejected.

### D4. Ratio and the floor of the denominator (reference, settled)

B2 = `ratio(wave n, wave n−1)`. The reference (owner's answer 13:58): B2 is empty when the wave n−1 value is `≤ 1e-6`, for both
B2.1 and B2.2; this covers zero and negative values (a negative mean area of wave n−1 makes B2 empty, not a sign flip). The existing
`ratio` is missing only when the right side is not finite or `≤ 0`, so a value in `(0, 1e-6]` would give a huge ratio that research
does not produce. The `ratio` operand therefore gets an optional `right_floor` (finite number, default 0): missing when
`right ≤ right_floor`. B2 sets `right_floor` 1e-6. `right_floor` enters the ratio identity only when set, so A1 and A2 ratios are
unchanged.

A numerator `ΔDI_n ≤ 0` (the new wave gained nothing) is a valid value ≤ 0 and is cut by a lower bound, which is the intent.

### D4a. DI smoothing (reference, settled)

The reference computes DI over the whole history, one series from the first bar of the dataset (`ewm(alpha 1/14, adjust=False)`,
first-bar TR `high − low`, DM 0, 0/0 → 0); the episode and the entry only pick `S*`/`P` from it. Engine's `di_plus`/`di_minus` use
a Wilder RMA with an SMA bootstrap. They converge: max |ΔDI| 0.026 after bar 100, 2.8e-5 after 200, 1.0e-8 after 300, 7.8e-12
after 400, 5.7e-14 after 1000, so below 1e-9 after about 320 bars; the earliest previous-wave `S*` among the reference entries is
bar 6293. **The existing `di_plus`/`di_minus` features are reused as they are, with no smoothing option**, on the condition that
DI is computed over the loaded history from the data start; if a caller truncates history before the entry, it keeps at least
about 400 bars before the earliest `S*` it needs (both waves). This is stated as a requirement on the live window, not as new
Engine behaviour: the existing feature warm-up rule already makes early values missing.

### D5. Direction of the cut

The bad side is LOW. The range block keeps both bounds nullable (`bounds exclusive`, `empty pass`); the Engine does not forbid a
high cut. The task says the high side marks good entries and must not be cut; that rule lives in the manifest (only `min` is
bound for B2), not in the Engine.

### D6. Cost

A `touch: previous` segment reads one more row per bar from the same touch table; no pass over bars is added. `from_start` costs
what the aggregate under it costs: O(n) for `sum`/`mean_per_bar`, O(n log n) build and O(1) per bar for `max`/`min` (the A2 sparse
table, depth bounded by the longest leg). A spec without `touch`, `by_side` or `from_start` has the same node set and the same
results as before. Live history: the previous touch lies inside the same episode, already covered by the episode requirement;
the DI features add their existing warm-up rule and nothing else.

### D7. Questions for the reference (before code)

Answered by the owner's research thread (13:58, `b2_di_wave_task.md`, "Answers to OpenSpec D7"); the reference rows carry the
intermediate values (DI at `S*`, max and mean of each wave, ΔDI and area of both waves) and win on any difference; a bar offset
found at parity is reported.

1. Wave n−1 comes only from the same episode (touch number − 1); empty on the first touch. Done in D1.
2. Denominator empty at `≤ 1e-6`, zero and negative included, for B2.1 and B2.2; the numerator may be zero or negative. Done in D4.
3. `D[S*]` is the trade-side DI on the `S*` bar itself, the first bar of the inclusive leg `S*…P`. Done in D3.
4. DI period 14 by default; 28 and 56 are parameters (no Engine change).
5. The impulse of wave n is `S*…P` inclusive on both ends, as in A1/A2.
