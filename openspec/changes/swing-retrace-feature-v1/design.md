## Context

Feature kinds are added through the canonical feature-kind contract (`indicators/feature_kinds.py`): math in the canonical
evaluator, one contract entry, a warm-up policy (`pre-entry-predicates-v1`, "Extension invariant for new feature kinds"). A kind
on a higher timeframe is computed on that timeframe's completed bars and aligned to the base grid by
`frame_ops.align_completed_to_base`. Predicates read plan columns with non-finite values mapped to NaN and are False on NaN.

## Decisions

### D1. One kind, swing geometry on its own timeframe

`swing_retrace` reads `high`, `low` and, for `ema_touch`, `close` of its own timeframe. It returns one float per completed bar.
Everything is measured in bars of that timeframe; no intrabar or base-bar information enters a higher-timeframe value, so the
completed-bar alignment gives no look-ahead by construction.

### D2. Definition (direction `up`)

For `down`, use `h' = −low`, `l' = −high`, and the touch condition `high ≥ EMA`; everything else is identical.

Left edge `L` at bar `i`:

- `window`: `L = i − bars`. Undefined while `i < bars`.
- `ema_touch`:
  - `t` = the last bar `j ≤ i` with a finite `EMA(touch_period)` and `low[j] ≤ EMA[j]`;
  - `a` = the first bar of the current uninterrupted run of strict order `EMA(p1) > EMA(p2) > …` over `stack_periods`, when the
    order holds at `i` (absent when `stack_periods` is not given or the order does not hold at `i`);
  - `L` = the later of `t` and `a` among those that exist;
  - undefined when neither exists or `L < i − bars`.

Then, on `[L, i]`:

- `P` = the first bar with the maximum `high` in `[L, i]`;
- `S` = the first bar with the minimum `low` in `[L, P]`;
- `H = high[P] − low[S]`; undefined when `H ≤ 0`;
- `impulse_bars = P − S + 1`, `retrace_bars = i − P`;
- `D = high[P] − min(low[P..i])`;
- `bar_ratio = retrace_bars / impulse_bars` (0 when the extreme is the current bar);
- `speed_ratio = (D / retrace_bars) / (H / impulse_bars)`; undefined when `retrace_bars = 0`.

Undefined values are NaN.

Counting convention. Both legs count bars inclusively on the impulse side and bars after the extreme on the retrace side. A
one-bar impulse is therefore legal (`impulse_bars = 1`), which a bar ratio on a higher timeframe needs. One convention serves
both measures.

### D3. Ties and determinism

First index on ties for both extremes. Same inputs give the same series.

### D4. Compute cost

Computed only when a spec requests it, once per feature identity per evaluation context, like any other feature. Every other
spec computes nothing new.

- `window`: both endpoints of `[L, i]` and of `[L, P]` are non-decreasing in `i`, so monotonic deques give O(n).
- `ema_touch`: `L` can move back when a stack run ends, so the range extremes use a sparse table: O(n log n) time, O(n log n)
  memory per requested identity, on the feature's own timeframe. On a higher timeframe `n` is the number of its bars, which is small.

The EMAs inside `ema_touch` use the canonical EMA math, not a second implementation. They are internal to the kind and are not
plan columns.

### D5. Identity

All six parameters enter the identity; `stack_periods` absent and `[]` are the same identity only if `[]` is rejected, so `[]` is
rejected. `touch_period` and `stack_periods` are rejected with `anchor: window`. The column label is
`swing_retrace_<tf>_<direction>_<measure>_<anchor>_<bars>[_t<touch_period>][_s<p1>-<p2>-…]`.

### D6. Undefined-means-allowed: an explicit predicate option

A rule "allow unless the ratio is at least X" is `compare {left: ratio, op: "<", right: X}`. On a bar where the ratio is undefined
it is False today, which turns "unknown" into "rejected". There is no negation to write "not (ratio ≥ X)".

Decision: an optional `if_missing: true` on `compare`, `range` and `change`. With it, the predicate is True on bars where an
operand is missing or non-finite; otherwise the comparison applies as before. Default `false` keeps every existing spec identical.
It is part of the predicate identity. It is not allowed on `state` (no operand), on `temporal` (the inner predicate carries it),
or in a `short` override (one missing-value policy per predicate).

Indicator warm-up is affected too: with `if_missing: true`, bars before the operand is ready are allowed. That is the stated
meaning of the option; a spec that wants warm-up to reject adds a separate ordinary predicate on a warmed-up feature.

Alternative considered: a companion kind returning 1/0 for "defined", combined by `composite_setup` paths ("ratio < X" OR
"defined < 0.5"). It needs no predicate change but doubles the paths per rule and makes every such rule two children. Rejected
for readability; it remains possible if the option is not wanted.

### D7. Side

The kind has an explicit `direction`. A predicate uses its existing `short` override to replace `left` with the `down` feature;
no automatic inversion is added.

## Example (illustration only)

```json
{"compare": {
  "left": {"feature": {"kind": "swing_retrace", "timeframe": "4h",
           "params": {"direction": "up", "measure": "bar_ratio", "anchor": "ema_touch",
                      "bars": 180, "touch_period": 20, "stack_periods": [20, 50, 100]}}},
  "op": "<", "right": {"const": 3}, "if_missing": true,
  "short": {"left": {"feature": {"kind": "swing_retrace", "timeframe": "4h",
            "params": {"direction": "down", "measure": "bar_ratio", "anchor": "ema_touch",
                       "bars": 180, "touch_period": 20, "stack_periods": [20, 50, 100]}}}}}}
```

## Risks

- A wrong extreme index changes every downstream value; mitigated by the per-bar reference loop (task 2.3).
- `if_missing: true` can let warm-up bars through; documented in D6 and covered by a scenario.
