## Why

The owner chose **vote B** for the EMA200 strategies (BTC, ETH, SOL; 2026-10-21): universal filters, universal linear weights,
block when the weighted sum reaches 0.75 or any veto fires. Ten of its filters have no Engine component, so vote B cannot run in
the Engine, on the demo or in Runtime. The brief is `/mnt/project-files/engine-tasks/ema200/vote_b_missing_components.md`; the
research definitions are `ema200_calib/*/code/altvals.py` (formulas, copied unchanged across coins) and the vote is
`ema200_calib/review/calib/{pick2.json, vetos.json, vote2.py}` (artifact "Как устроен голос Б").

| Filter | What it measures | Role in vote B |
|---|---|---|
| D1 | body of the forming daily candle in daily ATR | weight 0.86 at ≤ −0.274 |
| V1.1 | pullback volume sum ÷ impulse volume sum | weight 0.66 at ≤ 0.0574, veto ≤ 0.0441 |
| V1.2 | own-colour volume sum, pullback ÷ impulse | veto ≤ 0.0422 |
| V1.4 | mean of the top 10 % volumes, pullback ÷ impulse | veto ≤ 0.084 |
| C3.1 | pullback depth ÷ impulse height | weight 0.41 at ≥ 0.604 |
| C3.2 | C3.1 of this wave ÷ C3.1 of the previous wave | veto ≥ 3.43 |
| A3 | pullback speed ÷ impulse speed | weight 0.39 at ≥ 3.33, veto ≥ 15.8 |
| B3 | impulse height in ATR | weight 0.32 at ≤ 9.59, veto ≤ 4.65 |
| A5 | efficiency ratio of the pullback − of the impulse | weight 0.20 at ≥ 0.26 |
| A4 | pullback bars ÷ impulse bars | weight 0.15 at ≥ 10.3 |

The numbers in the table are context only. The Engine holds none of them: every level, weight, veto and the threshold come from
the strategy config (`weighted_vote_setup`). The components are atomic: each one is one value and knows nothing about its role.

## What Changes

Builds on the episode legs of A1/A2/B1/V1.3/C5 and on `ratio` with `right_floor`. No new indicator kind.

- **New operand `wave_measure`** `{episode, measure, touch?, atr?}` with five measures of the current wave:
  `impulse_atr` (B3), `speed_ratio` (A3), `duration_ratio` (A4), `efficiency_gap` (A5), `depth_share` (C3.1).
  `depth_share` also reads the previous wave of the same episode (`touch: previous`), so
  **C3.2 = `ratio(depth_share current, depth_share previous)`** with `right_floor` from the config (research uses 1e-6).
- **New operand `leg_volume`** `{episode, leg, aggregate, bars?, top_share?}`: the volume sum or the mean of the largest
  `top_share` of volumes over the impulse `[S*, P]` or the pullback `[P+1, t]` (the legs of `leg_mean`), over all bars or only
  bars of the leg's own colour. **V1.1, V1.2, V1.4 = `ratio(pullback, impulse)`** of the matching pair.
- **New operand `forming_candle`** `{timeframe, atr, episode?}`: the body of the candle of `timeframe` that contains `t`,
  from its first base bar to `t`, with the trade, divided by the Wilder ATR of the last closed candle before it.
  **D1 = `forming_candle` on `1d` with `atr_wilder` 14 on `1d`**.
- All three are accepted where `leg_mean` is: side of a `ratio`, operand of a `range` and of a `compare`, operand of a weighted
  vote input. Rejected as the operand of a `change`.
- **Weighted vote**: no change. Checked against vote B (design D6): max inside a voter, exact sum of weights, block at
  `score ≥ threshold` or any veto, inclusive levels, missing value votes nothing. The design gives the vote B config as an example.
- **Cost**: O(n) per series for everything except `top_mean`, which is O(n · L) for the pullback (L = leg length), computed only
  on bars with a valid wave. A spec without the new operands pays nothing.

Not in this change: catalog and manifest bindings, Research surfaces, deploy, MFI14 (B2 m14) and A6 (MACD area) of votes A / V / V2.
