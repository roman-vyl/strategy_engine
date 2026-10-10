## Context

- Indicators are computed once per evaluation by `RangeIndicatorEvaluator.evaluate_native`; each canonical kind has one
  `FeatureKindContract` entry (`indicators/feature_kinds.py`), a math branch (`_compute_feature`) and a live warm-up policy
  (`live_calculation/indicator_requirements.py`). ADX/DI shows the pattern for one calculation with several output kinds.
- The predicate layer (`strategies/ema_pullback/predicates.py`) reads plan columns, prices, constants and EMA-stack episode
  operands, and has the classes `compare`, `range`, `change`, `state`, `temporal`. `range` has required inclusive bounds and is
  False on a non-finite operand.
- The EMA-stack episode (`stack_episode.py`) is rebuilt per evaluation and holds, per side, the per-bar `touch_number` and a
  touch table with `origin_bar` (`S*`), `peak_bar` (`P`) and `touch_bar` per touch. It holds no metric, by spec.
- Research computes A1 per entry bar `b` with the episode's current touch (`touch_number[b]`) and its `S*`, `P`:
  impulse bars `S*..P`, pullback bars `P..b` (both inclusive), `h = hist` of MACD 48-78-48 on 5m closes with
  `ewm(span, adjust=False)`, sign flipped for shorts; A1 = `(Σ|h<0| on pullback / bars) ÷ (Σ h>0 on impulse / bars)`;
  missing when any `h` on either segment is NaN or the denominator is not positive. A band blocks `v ≤ low` or `v ≥ high`;
  a missing value is never blocked.

## Decisions

### D1. Blocks, not a setup

The owner's composition rule forbids per-indicator setups: a new indicator goes feature → predicate → composite. A1 is
therefore four reusable blocks (MACD kind, segment operand, ratio operand, range extension) used as one `composite_setup`
child. No new component id, no new allowlist entry.

### D2. MACD as three kinds of one calculation

`macd`, `macd_signal`, `macd_hist`, each requestable on its own, sharing one per-evaluation cache keyed by
`(timeframe, fast, slow, signal)` exactly like `adx`/`di_plus`/`di_minus`.

- Params `{fast, slow, signal}`: positive integers, `fast < slow`, no other keys, no dependencies; source `close` only
  (as RSI; other sources can be added later without changing identities of `close`).
- Math: `ema_f = close.ewm(span=fast, adjust=False).mean()`, same for `slow`; `macd = ema_f − ema_s`;
  `signal = macd.ewm(span=signal, adjust=False).mean()`; `hist = macd − signal`. This is the formula research used.
- Label `<kind>_close_<tf>_<fast>_<slow>_<signal>`, e.g. `macd_hist_close_5m_48_78_48`. Identity params
  `{fast, slow, signal}` plus the usual `timeframe` and `source`.
- Higher timeframe: completed-bar alignment through the existing `align_completed_to_base`.
- Warm-up (live): a two-stage EMA cascade, so the requirement is the EMA convergence bars of `slow` plus those of `signal`
  at the calibrated EMA tolerance (a sufficient bound; `fast < slow` converges first).
- Values exist from the first bar (EMA seeds on bar 0), as for `ema`.

### D3. Segment operand

Wire:

```json
{"segment": {
  "episode": "trend",
  "of": {"kind": "macd_hist", "timeframe": "5m", "params": {"fast": 48, "slow": 78, "signal": 48}},
  "from": "peak", "to": "current",
  "select": "negative_abs",
  "aggregate": "mean_per_bar"}}
```

- `episode` names a declared `ema_stack_episode` ref; `of` is a feature reference parsed by the canonical feature-kind
  contract (same schema as the `feature` operand).
- Points on bar `t` come from the touch-table row of the current touch `m = touch_number[t]` of the evaluated side:
  `origin = origin_bar[row]`, `peak = peak_bar[row]`, `current = t`. Allowed `(from, to)`: `(origin, peak)`,
  `(peak, current)`, `(origin, current)`. Any other pair is rejected.
- Segment `[a, b]` is inclusive; `bars = b − a + 1`. Since `S* ≤ P ≤ touch ≤ t`, every read bar is `≤ t`.
- Series: the plan column of `of`, multiplied by −1 on the short side. Selection maps each bar to a value:
  `all → h`, `positive → max(h, 0)`, `negative_abs → max(−h, 0)`.
- Aggregate over the selected values: `sum`, `mean_per_bar = sum / bars` (all bars of the segment, not only selected ones),
  `max` (so `max` of `positive` over a segment without positive bars is 0, consistent with `sum`).
- Missing (NaN) when the side's episode is inactive or censored on `t`, `m < 1`, either point is missing, or any value of
  the series on `[a, b]` is non-finite.
- `of` must be on the base timeframe (`base` or equal to the market base timeframe): a segment counts base bars, and an
  aligned higher-timeframe column would repeat values. Evaluation fails closed otherwise. Scales (×3, ×12, ×48) are expressed
  with the MACD periods on the base timeframe, as research does.
- Cost: O(n) for `sum` / `mean_per_bar` via prefix sums of the selected values and of a non-finite counter; `max` via a
  sparse table, O(n log n). Independent of segment lengths.
- Room for later: `"window": {"last_n": N}` or `{"top_fraction": q}` inside `segment`. Not part of this change; an unknown
  field is rejected today, so adding it later does not change any existing identity.

### D4. Ratio operand

`{"ratio": {"left": <operand>, "right": <operand>}}`. Each side is any operand of the layer except `ratio` itself (no
nesting in this change, keeping the layer away from an expression language) and not both constants. Value
`left / right`; NaN when either side is non-finite or `right ≤ 0` (a ratio of magnitudes; a non-positive denominator has no
meaning for the filters planned).

### D5. Range: optional bounds, bound mode, empty policy

```json
{"kind": "range", "operand": {...}, "min": 0.32, "max": null, "bounds": "exclusive", "empty": "pass"}
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

### D6. Identity and memo

- `predicate.segment`: params `{from, to, select, aggregate}`, upstream `{episode: <episode node of the side>,
  series: column_node(feature)}`, carries the side.
- `predicate.ratio`: params `{left, right}` as `_operand_param` tuples, upstream the nodes of non-constant sides; carries
  the side when any side does.
- An operand node is consumed through `compute_through` at the point its value is read; a ratio consumes its sides from
  inside its own compute. `PredicateIdentity.nested` lists, in evaluation order, every node the predicate's compute consumes,
  so the memo pre-pass predicts them (a ratio of two segments: ratio, segment, column, segment, column).
- Derived operand nodes are looked up by their position in the predicate (`operand`, `left`, `right`, `operand.left`, …),
  because a feature request is not hashable.
- The value trace (D7) consumes the operand node once more; that consumption is predicted too. If the node is no longer
  memoized the value is recomputed, never wrong.

### D7. Evidence for the chart

For a `composite_setup` child that is a `range` over a `segment` or `ratio` operand, the trace adds
`child:<child_id>:value`: the operand value per bar for the evaluated side, `null` when missing. Other children keep their
exact trace, so outputs of existing specs do not change.

### D8. Live history

A segment reads bars back to `S*` of the current touch. Those bars are inside the episode's own history (`history_bars`,
already a requirement of every declared episode) and the series' warm-up is counted per feature. A predicate over a segment
or ratio therefore contributes the explicit zero-additional entry, like any current-bar predicate.

### D9. Phase conditions

The new operands are ordinary operands, so `composite_phase_condition` children may use them. A child with a segment
operand needs the episode bundle, which `composites_need_context_bundle` detects through the operand tree. No other change.

## Acceptance procedure (owner's Mac, separate step)

1. Evaluate the A1 operand on the EMA500 strategy with episode `window_bars = break_bars = 48` over the full history;
   at every reference entry bar compare `S*`, `P` (touch-table row of the current touch) and A1 with
   `a1_engine_ref_{btc,eth}.csv.gz`, tolerance 1e-9.
2. Apply the band to the reference entries: ETH `(0.32, null)` → 459 blocked, BTC `(0.44, 3.5)` → 737,
   `(null, null)` → 0.
3. One Engine run of the ETH cell (EMA500, W9, lookback 140, SL 8, TP 6.5, band `(0.32, null)`) equals the replay on net,
   trades and win rate.

EMA seeding: research seeds every EMA on the first candle of the dataset (2021-03); the Engine seeds on the first bar of
its frame. Agreement to 1e-9 needs a frame that starts early enough; the acceptance run uses the full history.

## Alternatives not taken

- A monolithic `a1_band_setup`: forbidden by the composition rule and not reusable for A2–A6.
- Storing a metric in the episode projection: the projection spec keeps it metric-free.
- A general arithmetic expression operand: the layer rejects arithmetic expressions; one ratio is enough for A1–A6.
- `empty = pass` as the default: changes existing behaviour.

## Open questions for the owner

- **Q1. Composer catalog / slider.** The task asks for a slider 0–5, step 0.01, marks 0.15, 0.26, 0.32, 0.38, 0.44, 0.5,
  0.6, 1.2, 1.85, 2.3, 3.5, `null` = no control. The Engine catalog has no `composite_setup` entry and its field schema has
  no `step`, `marks` or `nullable`; Research and the front know no components and bind values through the manifest
  (`materialize.strategy_template` + `bindings` + `options`). Recommendation: no Engine catalog change in this change; the
  slider is the manifest's binding of `min` / `max` (with `null` as an option) on the A1 strategy template. Alternative:
  extend `ParamFieldSchema` with `step`, `marks`, `nullable` and add an A1 preset to the catalog.
- **Q2. `max` aggregate.** Defined over the selected values with non-selected bars as 0 (D3). Research has not used it yet.
