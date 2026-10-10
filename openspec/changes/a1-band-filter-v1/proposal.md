## Why

Research found that blocking entries whose pullback is too weak compared with its impulse raises win rate, R and net on both
coins (metric A1: ETH best low cut 0.32; BTC best pair low 0.44 and high 3.5). The owner wants this as a universal band filter
with two sliders, where each slider can be set to "no control", so it can be run on the Engine.

The Engine already computes atomic indicator series and already knows the EMA-stack episode points (`S*` origin, `P` peak).
What is missing is a way to read a series between two of those points. The filter is therefore built from reusable blocks,
not as a monolithic setup: the same blocks will later express A2/A3/A4/A6 and the leg variants "last N bars" and "top share
of bars".

## What Changes

- **MACD feature kinds** `macd`, `macd_signal`, `macd_hist` (one calculation group, like ADX/DI):
  `macd = EMA(close, fast) − EMA(close, slow)`, `signal = EMA(macd, signal)`, `hist = macd − signal`, with the Engine's own
  EMA (`ewm(span, adjust=False)`). Params `{fast, slow, signal}`, `fast < slow`, any supported timeframe, source `close`.
  Contract entry, math branch and a convergence warm-up policy, as the extension invariant requires.
- **Segment operand** (new predicate operand) `{"segment": {episode, of, from, to, select, aggregate}}`: the aggregate of one
  base-timeframe feature over the bars between two points of the current touch of an EMA-stack episode.
  - Points: `origin` (`S*`), `peak` (`P`), `current` (the evaluated bar). Allowed spans: `origin → peak`, `peak → current`,
    `origin → current`. Both ends inclusive, so bar `P` belongs to both the impulse and the pullback, as in research.
  - Side: for the short side the series is negated before selection.
  - `select`: `all` | `positive` (`h > 0`) | `negative_abs` (`|h|` for `h < 0`).
  - `aggregate`: `sum` | `mean_per_bar` (selected sum ÷ number of all bars of the segment) | `max`.
  - Missing (non-finite) when there is no current touch, the segment is empty, or any value on it is non-finite.
    Only bars `≤ t` are read; no lookback window.
  - The wire format leaves room for `last_n` and `top_fraction` bar windows later; they are not implemented now and are
    rejected as unknown fields.
- **Ratio operand** `{"ratio": {"left", "right"}}`: `left ÷ right`, missing if either side is missing or `right ≤ 0`.
- **Range predicate extended** (backward-compatible):
  - `min` and `max` may each be `null` ("no control"); both `null` passes every bar with a finite operand;
  - `bounds`: `inclusive` (default, current behaviour) | `exclusive`;
  - `empty`: `block` (default, current behaviour) | `pass` for a missing operand;
  - `min < max` when both are set and `bounds` is `exclusive`; `min ≤ max` stays for `inclusive`.
- **Evidence**: a `composite_setup` range child whose operand is a segment or a ratio adds its operand value per bar to the
  trace as `child:<child_id>:value`, for the chart.

A1 expressed with the blocks:

```
range(
  ratio(
    segment(macd_hist 5m 48-78-48, peak → current,  negative_abs, mean_per_bar),
    segment(macd_hist 5m 48-78-48, origin → peak,   positive,     mean_per_bar)),
  min = low | null, max = high | null, bounds = exclusive, empty = pass)
```

on the strategy's EMA-stack episode (research used `window_bars = break_bars = 48`).

Nothing changes for specs that use none of the new kinds, operands or range fields.

## Impact

- New capability `macd-indicator-vertical-slice-v1`.
- `pre-entry-predicates-v1`: MODIFIED `Supported predicate classes`, `Side semantics`, `Non-finite values are not satisfied`;
  ADDED `Segment operand shape`, `Segment points`, `Segment value`, `Ratio operand`, `Range bounds`, `Range empty policy`.
- `ema-pullback-composite-setup-v1`: MODIFIED `Evidence` (operand value trace).
- `batch-computation-reuse`: MODIFIED `Identity twins for predicates and composites`; ADDED
  `No compute regression without segment or ratio operands`.
- `live-calculation-window-planning`: MODIFIED `Recursive indicator convergence warm-up` (MACD cascade); ADDED
  `History policy for segment and ratio operands`.
- Not modified: `ema-stack-episode-v1` (the projection stays metric-free; the segment operand reads its points),
  `ema-pullback-feature-plan-v1` (the feature inside a segment is an ordinary predicate feature reference, planned like any
  other), `ema-pullback-composer-catalog-v1` (see design, open question Q1).
- Code: `indicators/implementations/macd.py`, `range_evaluator.py`, `feature_kinds.py`, `indicator_requirements.py`,
  `adapters/http/health.py`, `strategies/ema_pullback/predicates.py`, `setups.py` (trace), `managed_composite.py`
  (bundle detection), `live_calculation_requirements.py`, `evaluation.py` (memo pre-pass).

## Verification

- Unit tests: MACD against an independent pandas implementation on base and higher timeframes; segment aggregates long and
  short, every `select` × `aggregate`, empty segment, non-finite inside, no current touch; ratio with zero and negative
  denominator; range with `null` sides, both bound modes, both empty policies, and every existing range config unchanged;
  identity and memo (zero `unforeseen_consumptions`, memo on = memo off).
- Acceptance on the owner's data (Mac stack, separate step):
  1. A1 per EMA500 entry equals the research reference (`a1_engine_ref_btc.csv.gz` 2185 entries,
     `a1_engine_ref_eth.csv.gz` 1970 entries) to 1e-9, with matching `S*` and `P`.
  2. Block masks equal research: ETH `(0.32, null)` → 459 blocked; BTC `(0.44, 3.5)` → 737 blocked; `(null, null)` → 0.
  3. One Engine run equals the replay on net, trades and win rate: ETH EMA500, W9, lookback 140, SL 8, TP 6.5,
     band `(0.32, null)`.
- Gate: ruff, mypy, the full suite (without `tests/parity`), `openspec validate a1-band-filter-v1 --strict`.
