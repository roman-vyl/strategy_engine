## Why

Research found that blocking entries whose pullback is too slow compared with its impulse raises win rate, R and net on both
coins. After comparing ten variants cell by cell the owner chose signed Δ(EMA5 − anchor EMA) over the last 75 bars of each leg
(BTC cut 0.9, ETH cut 1.2). The owner wants it as a universal band filter with two sliders, each of which can be set to "no
control", so it can be run on the Engine.

The Engine already computes atomic indicator series (`ema`) and already knows the EMA-stack episode points (`S*` origin, `P`
peak). What is missing is a way to read a series between two of those points. The filter is therefore built from reusable
blocks, not as a monolithic setup.

## What Changes

No new indicator kind. MACD is not part of this change.

- **Segment operand** (new predicate operand)
  `{"segment": {episode, of, from, to, aggregate, window?, value?, negate?}}`: the aggregate of one base-timeframe series over
  the bars between two points of the current touch of an EMA-stack episode.
  - `of`: a feature reference, or `{"difference": {"left": <feature>, "right": <feature>}}` = `left − right` per bar
    (A1: EMA(close, 5) − EMA(close, 500)).
  - Points: `origin` (`S*`), `peak` (`P`), `current` (the evaluated bar). Allowed spans: `origin → peak`, `peak → current`,
    `origin → current`. Both ends inclusive, so bar `P` belongs to both the impulse and the pullback.
  - `value`: `level` (default, the series itself) | `change` (per-bar change `Δ[t] = x[t] − x[t−1]`).
  - `window`: `null` (default, the whole leg) | `{"last_n": N}` (the last N bars of the leg, ending at the end point; a shorter
    leg is used whole).
  - `aggregate`: `sum` | `mean_per_bar` (sum ÷ number of bars in the window).
  - `negate`: `true` flips the sign of the result (default `false`).
  - Side: for the short side the series is negated before everything else.
  - Missing when there is no current touch, the window is empty, or any value used is non-finite. Only bars `≤ t` are read.
  - All bars take part with their sign; there is no selection by sign.
- **Ratio operand** `{"ratio": {"left", "right"}}`: `left ÷ right`, missing if either side is missing or `right ≤ 0`.
- **Range predicate extended** (backward-compatible):
  - `min` and `max` may each be `null` ("no control"); both `null` passes every bar with a finite operand;
  - `bounds`: `inclusive` (default, current behaviour) | `exclusive`;
  - `empty`: `block` (default, current behaviour) | `pass` for a missing operand;
  - `min < max` when both are set and `bounds` is `exclusive`; `min ≤ max` stays for `inclusive`.
- **Evidence**: a `composite_setup` range child whose operand is a segment or a ratio adds its operand value per bar to the
  trace as `child:<child_id>:value`, for the chart.

A1 expressed with the blocks (long; the short side negates the series inside the segment):

```
range(
  ratio(
    segment(EMA5 − EMA500, peak → current, change, last_n 75, mean_per_bar, negate),
    segment(EMA5 − EMA500, origin → peak,  change, last_n 75, mean_per_bar)),
  min = low | null, max = high | null, bounds = exclusive, empty = pass)
```

on the strategy's EMA-stack episode (research used `window_bars = break_bars = 48`). `fast = 5` and `last_n = 75` are
parameters. Default settings (owner): low 0.4 … 1.2 step 0.1, high 6 / 9 / 12 / 15, each side also `null`; the default
selection is both sides `null`.

Nothing changes for specs that use none of the new operands or range fields.

## Impact

- `pre-entry-predicates-v1`: MODIFIED `Supported predicate classes`, `Side semantics`, `Non-finite values are not satisfied`;
  ADDED `Segment operand shape`, `Segment source fields`, `Segment aggregation fields`, `Segment points`, `Segment window`, `Segment value`, `Ratio operand`, `Range bounds`, `Range empty policy`.
- `ema-pullback-composite-setup-v1`: MODIFIED `Evidence` (operand value trace).
- `batch-computation-reuse`: MODIFIED `Identity twins for predicates and composites`; ADDED
  `No compute regression without segment or ratio operands`.
- `live-calculation-window-planning`: ADDED `History policy for segment and ratio operands`.
- Not modified: `ema-stack-episode-v1` (the projection stays metric-free; the segment operand reads its points),
  `ema-pullback-feature-plan-v1` (the series inside a segment are ordinary predicate feature references, planned like any
  other), `ema-pullback-composer-catalog-v1` (see design, open question Q1), the feature-kind contract (no new kind).
- Code: `strategies/ema_pullback/predicates.py`, `setups.py` (trace), `managed_composite.py` (bundle detection),
  `live_calculation_requirements.py`, `evaluation.py` (memo pre-pass).

## Verification

- Unit tests: the EMA-difference series; signed segment mean with `last_n` longer and shorter than the leg and `null` (whole
  leg); long and short; empty leg and non-finite inside; no current touch; impulse mean ≤ 0; ratio with zero and negative
  denominator; range with `null` sides, both bound modes, both empty policies, and every existing range config unchanged;
  identity and memo (zero `unforeseen_consumptions`, memo on = memo off).
- Acceptance on the owner's data (Mac stack, separate step; reference files and generator in the task text):
  1. A1 per EMA500 entry equals `a1s_engine_ref_btc.csv.gz` (2185 entries, 2016 with a value) and
     `a1s_engine_ref_eth.csv.gz` (1970, 1811) to 1e-9, with matching `S*` and `P`; NaN in the reference is NaN in Engine.
  2. Block counts equal research: BTC `(0.9, null)` = 1079, `(0.9, 10)` = 1179, `(null, 10)` = 100; ETH `(1.2, null)` =
     1114; `(null, null)` = 0.
  3. One Engine run equals the replay: BTC EMA500, W7, lookback 130, SL 7, TP 5.5, band `(0.9, 10)` → 205 trades, win rate
     23.41%, net $37,498.35 (no filter: 368 trades, $17,458.30).
- Gate: ruff, mypy, the full suite (without `tests/parity`), `openspec validate a1-band-filter-v1 --strict`.
