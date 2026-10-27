## Context

- Research: `review/emaslope/feat.py`. The EMA is `o[0] = close[0]`, `o[i] = o[i−1] + a·(close[i] − o[i−1])`, `a = 2/(n+1)`.
  `b` is the last closed bar before the entry, P the peak bar, `s0 = max(P, b − x)`, `s1 = b`, valid only if `s1 > s0`.
- The `segment` operand with `value: change` reads `x[e] − x[s − 1]` with `s = max(P, e − last_n + 1)`. When the window is clipped,
  it starts one bar before P and does not divide by `x[s0]`, so it cannot give these values.

## Decisions

### D1. Operand `window_change`

`{"window_change": {"episode", "of", "last_n", "form"}}`, all required, no other field. `of` is a base-timeframe feature,
`last_n` a positive integer, `form` is `change` or `slope`. The window is the last `last_n` steps of the pullback of the current
touch, never earlier than P. The value is signed by side like the other leg operands (impulse direction positive). It is accepted
wherever a ratio is accepted, and rejected as the operand of a `change`.

Rejected: a `form: per_height` that divides by the impulse height inside the operand. The height is already readable from the
episode (`wave` `peak_price` and `origin_price`), so the config composes it with `ratio`, `abs` and `difference`.

### D2. Identity

Own node family `predicate.window_change` with params `last_n` and `form`, upstream the episode and the feature column, side set.

### D3. Parity reference

`/mnt/project-files/engine-tasks/ema200/ema_slope/ref_<coin>.csv.gz` (all entries of BTC, ETH, SOL). The research EMA starts at
the first candle of the history; the Engine EMA is computed over the same history in the parity run. Tolerance 1e-9 relative,
NaN equal.
