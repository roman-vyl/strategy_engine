## Context

- The predicate layer (`strategies/ema_pullback/predicates.py`) reads plan columns, prices, constants and EMA-stack episode
  operands, and has the classes `compare`, `range`, `change`, `state`, `temporal`. `range` has required inclusive bounds and is
  False on a non-finite operand. Feature operands go through the canonical feature-kind contract; `ema` is already a kind.
- The EMA-stack episode (`stack_episode.py`) is rebuilt per evaluation and holds, per side, the per-bar `touch_number` and a
  touch table with `origin_bar` (`S*`), `peak_bar` (`P`) and `touch_bar` per touch. It holds no metric, by spec.
- Research (revision 2, owner 2026-10-10) computes A1 per entry bar `t` with the episode's current touch and its `S*`, `P`:
  `d = EMA(close, 5) − anchorEMA` on 5m, `Δ[t] = d[t] − d[t−1]`, the last 75 bars of each leg (impulse `S*..P`, pullback
  `P..t`, both inclusive), all bars with their sign, mean per bar; A1 = `(−mean Δ pullback) ÷ (mean Δ impulse)`, for a short `d`
  is negated first. Missing when no wave, a window is empty, any value is NaN, or the impulse mean is ≤ 0. A band blocks
  `v ≤ low` or `v ≥ high`; a missing value is never blocked.

## Decisions

### D1. Blocks, not a setup; no new indicator

The owner's composition rule forbids per-indicator setups: a new indicator goes feature → predicate → composite. A1 is
therefore three reusable blocks (segment operand, ratio operand, range extension) used as one `composite_setup` child. No new
component id, no new allowlist entry, and no new feature kind: owner 2026-10-10 21:01, MACD is not needed. The EMAs are two
ordinary `ema` features of the plan (`close`, periods 5 and 500, base timeframe).

### D2. Segment operand

Wire:

```json
{"segment": {
  "episode": "trend",
  "of": {"difference": {
    "left":  {"kind": "ema", "params": {"period": 5}},
    "right": {"kind": "ema", "params": {"period": 500}}}},
  "from": "peak", "to": "current",
  "value": "change",
  "window": {"last_n": 75},
  "aggregate": "mean_per_bar",
  "negate": true}}
```

- `episode` names a declared `ema_stack_episode` ref.
- `of` is either a feature reference (same schema as the `feature` operand) or `{"difference": {"left", "right"}}`, two
  feature references; the series is `left − right` per bar. Every feature must be on the base timeframe
  (`base` or the market base timeframe) because a segment counts base bars and an aligned higher-timeframe column repeats
  values; another timeframe fails closed. The anchor named in `right` is explicit; it is normally the episode's anchor EMA.
- Points on bar `t` come from the touch-table row of the current touch `m = touch_number[t]` of the evaluated side:
  `origin = origin_bar[row]`, `peak = peak_bar[row]`, `current = t`. Allowed `(from, to)`: `(origin, peak)`,
  `(peak, current)`, `(origin, current)`. Any other pair is rejected.
- Leg `a..e` is inclusive. Window start `s = a` for `window = null`, and `s = max(a, e − N + 1)` for `{"last_n": N}`
  (`N` a positive integer); a leg shorter than `N` is used whole. `bars = e − s + 1`. Since `S* ≤ P ≤ touch ≤ t`, every read
  bar is `≤ t`.
- Series `x` = the plan column(s) per `of`, multiplied by −1 on the short side (before everything else).
- `value = level`: aggregate over `x[s..e]`. `value = change`: aggregate over `Δ[u] = x[u] − x[u−1]`, `u = s..e`.
  `Δ[s]` reads `x[s−1]`, the bar before the window (a bar of the leg, or the bar before the leg when `s = a`).
- `aggregate = sum`: the sum; `mean_per_bar`: the sum ÷ `bars`. For `change`, the sum telescopes to `x[e] − x[s−1]`, which is
  how it is computed.
- `negate = true` multiplies the result by −1 (after the aggregate). Default `false`.
- Missing (NaN) when the side's episode is inactive or censored on `t`, `m < 1`, a point is missing, or any `x` used
  (`x[s..e]` for `level`, `x[s−1..e]` for `change`) is non-finite.
- Selection by sign is not part of this change (the owner dropped the variants "with the trend only / against the trend only"
  and "top 50% of bars"). Adding a `select` or another `window` kind later is additive and changes no existing identity.
- Cost: O(n) with prefix sums of `x` and of a non-finite counter, independent of leg lengths.
- Boundary convention to be fixed by the reference: whether `Δ` at the end bar is included and whether `x[s−1]` is read are
  defined as above; if the reference of acceptance 1 disagrees, the reference wins and the difference is reported
  (the change is then limited to this decision).

### D3. Ratio operand

`{"ratio": {"left": <operand>, "right": <operand>}}`. Each side is any operand of the layer except `ratio` itself (no
nesting, keeping the layer away from an expression language), and not both constants. Value `left / right`; NaN when either
side is non-finite or `right ≤ 0`. For A1 the impulse mean ≤ 0 therefore gives a missing value, and with `empty = pass` the
bar is not blocked.

### D4. Range: optional bounds, bound mode, empty policy

```json
{"kind": "range", "operand": {...}, "min": 0.9, "max": null, "bounds": "exclusive", "empty": "pass"}
```

- `min` and `max` stay required keys but may be `null` = no control on that side. Existing configs carry numbers and are
  unchanged.
- `bounds`: `inclusive` (default; `min ≤ v ≤ max`) or `exclusive` (`min < v < max`). A `null` side imposes nothing.
- `empty`: `block` (default; a non-finite operand is False) or `pass` (True). This is the only place in the layer where a
  missing operand can be True, and only by explicit opt-in; there is still no negation.
- Validation: with both set, `min ≤ max` for `inclusive`, `min < max` for `exclusive`.
- `short` override may replace `min`, `max`, `bounds` and `empty`.
- Identity: `bounds` and `empty` enter the `predicate.range` params only when they differ from the default, and a `null`
  bound is carried as `None`; every existing range identity is therefore unchanged.

### D5. Identity and memo

- `predicate.segment`: params `{from, to, value, window, aggregate, negate}`, upstream `{episode: <episode node of the side>,
  series: column node(s) of `of`}`, carries the side. A `difference` carries its two column nodes in the roles `left`, `right`.
- `predicate.ratio`: params `{left, right}` as `_operand_param` tuples, upstream the nodes of non-constant sides; carries
  the side when any side does.
- An operand node is consumed through `compute_through` at the point its value is read; a ratio consumes its sides from
  inside its own compute. `PredicateIdentity.nested` lists, in evaluation order, every node the predicate's compute consumes,
  so the memo pre-pass predicts them.
- Band candidates that differ only in `min` / `max` share the EMA columns, both segments and the ratio.
- The value trace (D6) consumes the operand node once more; that consumption is predicted too. If the node is no longer
  memoized the value is recomputed, never wrong.

### D6. Evidence for the chart

For a `composite_setup` child that is a `range` over a `segment` or `ratio` operand, the trace adds
`child:<child_id>:value`: the operand value per bar for the evaluated side, `null` when missing. Other children keep their
exact trace, so outputs of existing specs do not change.

### D7. Live history

A segment reads bars back to `S*` of the current touch (and one bar further for `change`). Those bars are inside the episode's
own history (`history_bars`, already a requirement of every declared episode), and the EMA warm-up is counted per feature. A
predicate over a segment or ratio therefore contributes the explicit zero-additional entry, like any current-bar predicate.

### D8. Phase conditions

The new operands are ordinary operands, so `composite_phase_condition` children may use them. A child with a segment
operand needs the episode bundle, which `composites_need_context_bundle` detects through the operand tree.

## Acceptance procedure (owner's Mac, separate step)

Files are in `/Users/mcroma/BBB_data/research/analysis/BTCUSDT.P/book_metrics_v6/treatise/`; the exact names, counts and
columns are in the task text (`engine-tasks/a1_band_filter_task.md`).

1. Evaluate the A1 operand on the EMA500 strategy with episode `window_bars = break_bars = 48` over the full history; at every
   reference entry compare `S*`, `P` and A1 with `a1s_engine_ref_{btc,eth}.csv.gz` (columns `bar, time_ms, side, s_bar, p_bar,
   a1s`), tolerance 1e-9; a NaN in the reference is NaN in Engine.
2. Apply the band to the reference entries (key meta `<low idx>_<high idx>` in `btc_w48/levels_btc_a1sl75.json`,
   `eth_w48/levels_eth_a1sl75.json`; eligible 2168 BTC, 1953 ETH): BTC `(0.9, null)` = 1079, `(0.9, 10)` = 1179,
   `(null, 10)` = 100; ETH `(1.2, null)` = 1114; `(null, null)` = 0.
3. One Engine run of BTC EMA500, W7, lookback 130, SL 7, TP 5.5 (SL in ATR48, TP = ratio × SL, fee 0.04% per side, $10,000
   full equity), band `(0.9, 10)` equals the replay (`btc_w48/out_btc_a1sl75.csv.gz`): 205 trades, win rate 23.41%, net
   $37,498.35; without the filter 368 trades, $17,458.30.

EMA seeding: research seeds every EMA on the first candle of the dataset; the Engine seeds on the first bar of its frame.
Agreement to 1e-9 needs a frame that starts early enough; the acceptance run uses the full history.

## Alternatives not taken

- A monolithic `a1_band_setup`: forbidden by the composition rule and not reusable for A2–A6.
- A new `ema_difference` feature kind: a segment-level `difference` keeps the feature-kind contract untouched; the
  difference of two plan columns is not an indicator.
- MACD kinds: removed by the owner's revision.
- Storing a metric in the episode projection: the projection spec keeps it metric-free.
- A general arithmetic expression operand: the layer rejects arithmetic expressions; one ratio and one difference are enough.
- `empty = pass` as the default: changes existing behaviour.

## Open questions for the owner

- **Q1. Slider and default grid.** Defaults from the owner: low 0.4 … 1.2 step 0.1, high 6 / 9 / 12 / 15, each side `null`,
  default selection both `null`. The Engine accepts any finite value or `null`; its catalog has no `composite_setup` entry and
  its field schema has no `step`, `marks` or `nullable`, and Research and the front bind values through the manifest
  (`materialize.strategy_template` + `bindings` + `options`). Recommendation: no Engine catalog change; the grid is the option
  list of the manifest binding of `min` / `max` (with `null`). Alternative: extend `ParamFieldSchema` with `step`, `marks`,
  `nullable` and add an A1 preset to the catalog.
