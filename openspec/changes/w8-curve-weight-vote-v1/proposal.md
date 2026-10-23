## Status

DRAFT for the owner's decision. No code until the owner's word.

## Why

Vote **W8 variant 6** does not give a voter one fixed weight per threshold step, as vote B does. Each voter's weight grows smoothly
with how bad its value is:

- `e` = the "excess" of the stop share over the coin's base (percentage points) read from the voter's black curve at the entry's
  value (piecewise linear between grid points, negative excess counted as 0);
- weight `w = (exp(k · e) − 1) / (exp(k · e_v) − 1)`, no cap; `k` and `e_v` per voter from config;
- block when the sum of the 12 weights is ≥ 1.5, or any of the 9 vetoes of vote B fires (vetoes unchanged).

`weighted_vote_setup` today supports only step weights. Many steps could approximate the curve but would not equal research.

## What Changes (proposed)

1. A vote input MAY carry `curve {grid, excess, k, e_v}` instead of `steps`: the weight is computed as above from the operand value.
   `grid` strictly increasing, `excess` the same length; outside the grid the end value is used (as `np.interp`); a missing value
   weighs 0. The weight is a float (the step weights stay exact decimals).
2. A vote input MAY carry `when`: a list of `range` conditions over other operands; the input weighs 0 unless all hold. D1v is
   `forming_candle 1d` with `when` `completed_candle 1d body ≥ 1` and `completed_candle 1d close_position ≥ 0.85`.
3. The trace keeps `input:<id>:value`, `input:<id>:weight`, and adds `input:<id>:excess`.

## Config of variant 6 (from research, no numbers in the Engine)

| voter | side | k | e_v | curve |
|---|---|---|---|---|
| W8_30, W8_14, W8r | low | 0.15 | 16 | `oi/w8/var/excess_var.json` key `<name>|low` |
| W8p | low | 0.15 | 16 | `oi/w8/research/excess.json` |
| kI, W1r, W1d | kI low, W1r/W1d high | 0.3 | 16 | same |
| W2d | low | 0.6 | 16 | same |
| O1 | low | 0.6 | 20 | same |
| PS_R | high | 0.01 | 16 | same |
| D1v | low | 0.2 | 8 | same |
| Wk | high | 0.2 | 10 | same |

Threshold 1.5. Vetoes: a1s ≤ −0.0125, c5 ≥ 0.685, a3 ≥ 15.8, v11 ≤ 0.0441, v12 ≤ 0.0422, v13 ≤ 0.0747, v14 ≤ 0.084, b3h ≤ 4.65,
c32 ≥ 3.43.

## Parity reference

Block masks of variant 6: `review/surf/w8vote/maskwin6_<c>.npz` (BTC 774, ETH 669, SOL 702 blocked entries); per-voter values and
weights: `review/oi/w8/v6doc/comp6.json`; reference cell ETH W4 LB140 SL4.75 TP3R touches ≤ 3 + v6 = 438 trades, $23,790.73.
