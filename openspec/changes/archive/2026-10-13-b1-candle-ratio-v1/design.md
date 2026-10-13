## Context

- A1 (`a1-band-filter-v1`) and A2 (`a2-shape-aggregates-v1`, Engine e00defc, deployed) give `segment`, `ratio` and `range` over
  the legs of the current touch of a declared EMA-stack episode: impulse `S* … P`, pullback `P … t`; only bars ≤ t are read; the
  short side mirrors the series.
- Research reference (owner's Mac, `book_metrics_v6/b1/b1_values.py`, functions `frame` and `maxbody`; per-entry export
  `b1_engine_ref_btc.csv.gz`, replay cells and blocked counts in `b1_parity_btc.json`) fixes the exact formulas. Where this design
  and the reference disagree, the reference wins and the difference is reported; the decisions marked "reference" below are the
  ones the reference may overrule. The Mac files were not readable from the cloud when this was written; the almanac card B1
  (research-results-artifacts, branch `claude/project-thread-xwlq76`, `almanac/almanac.html`) and the task text were.
- Engine already has `atr` features for any timeframe, resampled from the base bars (`resample_ohlcv`, left-labelled, left-closed)
  and aligned to the base bars by `align_completed_to_base`: the value on a base bar is the ATR of the last candle of that
  timeframe that has closed by that bar.

## Decisions

### D1. A new operand `candle`, not a new aggregate of `segment`

A segment aggregates a one-dimensional series over a window of bars. B1 aggregates over candles that exist only inside a leg
(a 1h candle is clipped to the leg and its open and close come from the leg's first and last bars in the bucket). That is a
different object, so it gets its own operand with its own node family, carrying the episode, the leg, the timeframe, the
direction and the ATR column in its identity. `ratio` and `range` accept it wherever they accept a segment.

Wire form:

```
{"candle": {"episode": "trend", "leg": "pullback" | "impulse", "timeframe": "15m",
            "direction": "with" | "against", "atr": {"kind": "atr_wilder", "timeframe": "15m", "params": {"period": 14}}}}
B1_TF = ratio( candle(pullback, against, TF), candle(impulse, with, TF) )
```

`atr` is a feature reference like those of `segment.of` and is collected by the feature planner. Its kind SHALL be `atr_wilder` and
its timeframe SHALL equal the operand's `timeframe` (D5). Not set: the operand returns the raw largest body in price units.

### D2. Legs (reference)

- `impulse` = bars `S* … P` inclusive; `pullback` = bars `P+1 … t` inclusive (task text, reference `maxbody`). The peak bar belongs
  to the impulse only. At `t = P` the pullback has no bars and the operand is missing.
- Whole legs: no `last_n` window.
- Only bars ≤ t. For a touch the impulse is fixed, so its value is computed once per touch row and broadcast to every bar of the
  touch; the pullback value grows with `t`.
- The impulse starts at `S*`, with no search for the lowest low (reference answer; the almanac picture is only an illustration).
  A candle is clipped to open at `max(candle start, S*)` and to close at `min(candle end, P)`. The pullback is `P+1 … t`, empty
  when `t = P`.

### D3. Candles of a leg

For a timeframe of `m` base bars the base bars are bucketed by their open time on the timeframe grid (epoch-aligned, left-closed,
the same grid as `resample_ohlcv`). Inside one bucket only the bars that belong to the leg and are ≤ t build the candle:
open = open of the first such bar, close = close of the last such bar. High and low are not needed. So:

- a candle that opened before the leg is clipped at the leg start;
- a candle still forming at `t` has its close at bar `t` (its value is the value as of that bar, updated every base bar);
- for the impulse the candle that contains `P` is clipped at `P`.

Timeframe equal to the base timeframe gives the base candles. A timeframe that is not a multiple of the base timeframe is rejected.

### D4. Body and direction

Body with the trade (long): `close − open` when `> 0`; body against the trade (long): `open − close` when `> 0`. The short side
negates the sides (with = `open − close`, against = `close − open`). The operand is the largest such body over the candles of the
leg, floor 0; with `atr` set each candle's body is divided by that candle's ATR first (D5), then the maximum is taken.

- A leg without a candle in the wanted direction gives 0, a valid value. A pullback without a candle against the trade gives
  `B1 = 0` (nothing to cut). An impulse without a candle with the trade gives 0 as a denominator and `ratio` makes it missing
  (right ≤ 0), so the bar is not blocked, matching the task ("NaN if the impulse has no candle with the trade").
- A non-finite open or close in a candle that enters, or a missing `ATR_TF`, makes the operand missing.

### D5. ATR normalisation (reference, settled)

The reference (`b1_values.py` `frame`, `maxbody`, owner's Mac, answer 14:3x) divides **every clipped candle by the ATR14 of its own
timeframe at that candle**, not once at `t` or at `P`:

- a candle whose clip ends on its own last base bar (the bucket has ended by the end of the leg, and by `t`) uses the ATR of that
  same candle;
- a candle still forming at the leg edge uses the ATR of the previous, last closed candle (candle `k − 1`);
- candles whose ATR is not yet defined (the first 14 candles of the series) are skipped, not turned into a missing operand;
- the operand is `max over candles of (body ÷ ATR of the candle)`, for the impulse and the pullback alike. ATR does **not** cancel,
  B1 is not a plain body ratio.

The ATR is Wilder over timeframe candles: the first candle's true range is `high − low`, the seed is the mean of the first 14
true ranges, then `atr = (atr · 13 + tr) / 14`. Engine's `atr` feature is `true_range.rolling(period).mean()`, a simple
average, so it does **not** reproduce this (reading `indicators/implementations/atr.py`). The change therefore adds a feature kind
`atr_wilder` (parameters `period` only, label `atr_wilder_close_{timeframe}_{period}`, resampled on the same grid as the other
timeframe features), and the `candle` operand reads it per candle on the timeframe grid, so no base-bar alignment look-ahead is
involved: the ATR of a complete candle is known at its close. `atr` and everything that uses it stay unchanged. The seed and the
candle grid are the first thing checked at parity (task 4.1); a difference is reported.

Alternative considered: keep the SMA `atr` and accept a mismatch. Rejected: the owner's parity targets are in the Wilder ATR.

### D6. Computation and cost

Per timeframe and per bar, O(1) amortised work:

- for each touch row, a pass over its bars computes the running maximum of `with` and of `against` bodies over the candles
  that are complete (their bucket ended before the bar) and the body of the forming candle at the bar, and the operand at `t`
  is the maximum of the two;
- the impulse is one such pass over `S*…P`, broadcast;
- each candle's body is divided by its own ATR (D5) before it enters a running maximum, so the pass keeps the running maximum of
  normalised bodies, not of raw bodies;
- the passes are vectorised across touches (a segmented scan), so the total is O(n), independent of leg length, with one
  per-candle ATR lookup per bucket.

A spec without a `candle` operand adds no node and no work. Live history: the operand reads bars of the current touch, like a
segment, so it adds no history requirement beyond the `atr` feature the spec declares.

### D7. Identity and sharing

The operand has its own node family `predicate.candle`; its identity carries the episode identity, the leg, the timeframe, the
direction and the ATR column identity, and its upstream is the episode, the market bars and the ATR column. Candidates that differ
only in a threshold share the operand, the ratio and the columns, exactly as the A1/A2 bands do. Labels never enter an identity.

## Risks

- The ATR seed and the candle grid of the new `atr_wilder` feature must equal the reference's; a one-candle offset would shift
  every value. Mitigation: parity task 4.1 compares ATR values on the same candles first.
- The first pullback bar after the peak: a 1h candle opened at `P−3` and still forming at `P+1` has, in the pullback, only the
  bars from `P+1`. This clipping is by the task text and is covered by a boundary test.
- Timeframe grid alignment of candles depends on `time_ms` in the evaluation frame; a frame with gaps in the base series builds
  candles from the bars that exist (no filling), which is stated in the spec and tested.
