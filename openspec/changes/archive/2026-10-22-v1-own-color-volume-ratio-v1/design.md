## Context

- `leg_sum` (V1.1, archived `2026-10-22-v1-volume-sum-ratio-v1`) sums a base-bar series over `[S*, P]` or `[P+1, t]`.
- Research reference: `altvals.py`, `GV = cumsum(where(C > O, VOL, 0))`, `RV = cumsum(where(C < O, VOL, 0))`,
  `wi = seg(GV if long else RV, S, P)`, `wr = seg(RV if long else GV, P+1, b)`, `v12 = wr / wi` when `b > P` and `wi > 0`.

## Decisions

### D1. A field of `leg_sum`, not a new operand

Same legs, same prefix sums, same missing rules; only the summed series differs. As V2.2 did with `leg_mean`, the series is a field.
The field is side- and leg-dependent: the series is built per side and per leg from `open`, `close` and `volume`:
`volume[u]` where `g · (close[u] − open[u]) > 0` (impulse) or `< 0` (pullback), `g` = +1 long, −1 short; else 0; non-finite when
`open`, `close` or `volume` is not finite. The node identity already carries `leg`, `field` and the side.

### D2. V1.2

`ratio(leg_sum(pullback, own_color_volume), leg_sum(impulse, own_color_volume))`. Impulse sum 0 (no with-trade candle with volume):
the ratio is missing. A pullback with no counter candle gives 0, a value. No threshold is held by the Engine.

### D3. Grid

Research reads a forward-filled grid; a filled bar has `open = close` and volume 0, so it never counts. No difference is expected;
any found at parity is reported.
