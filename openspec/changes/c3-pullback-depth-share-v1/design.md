## Context

- Research reference: `altvals.py`:
  `ext = L[P:b+1].min() if g > 0 else H[P:b+1].max()`; `c31 = ((Pp − ext) if g > 0 else (ext − Pp)) / Hs`, `Hs = |Pp − Sp|`,
  computed only when `Hs > 0`. `Sp`, `Pp` are the origin and peak prices of the wave (low of `S*` and high of `P` for long).
- The touch table carries `origin_price` and `peak_price` in market units on both sides (C5 reads `peak_price` the same way).

## Decisions

### D1. Operand `pullback_depth`

`{"pullback_depth": {"episode"}}`, `episode` required, no other field. Value on bar `t`:
`g · (peak_price − ext[t]) / |peak_price − origin_price|` with `ext[t] = min(low[P..t])` long, `max(high[P..t])` short. The bar `P`
is part of the range, as in research; at `t = P` the value is defined (`ext` is the peak bar's own low or high).

Rejected: a generic `segment` of `low` with `ratio`. `ratio` does not subtract and must not nest, and the depth needs the peak
price from the touch table; one operand with the research formula keeps parity simple.

### D2. Computation

For each bar with a valid wave, the extreme is carried from the previous bar when it belongs to the same touch (same `P`) and
`t` grows by one; otherwise it is rebuilt over `[P, t]`. O(bars) in practice.

### D3. Identity

Own node family `predicate.pullback_depth`, no params, upstream the episode and the market bars.

### D4. Later: C3.2

C3.2 divides C3.1 by the same depth of the previous wave measured over `[P0, S*]`. It will extend this operand with a `touch`
field in its own change; nothing here depends on it.
