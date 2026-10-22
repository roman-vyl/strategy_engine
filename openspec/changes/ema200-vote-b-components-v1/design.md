## Context

- The episode gives, per touch row, `origin_bar` (S*), `origin_price` (the low of S* for a long, the high for a short),
  `peak_bar` (P) and `peak_price` (the high of P for a long, the low for a short). `t` is the evaluated bar (the entry bar `b` of
  research). `g` = +1 long, −1 short. `H = |peak_price − origin_price|`, the impulse height.
- Research reference: `altvals.py` (identical in `ema200_calib/bch200_20261021/code`, `btc_recheck/code`, `runs_20261020/*/code`).
  Its `s_price`, `p_price`, `s_bar`, `p_bar` are the same points as A1/A2/B1 use (parity of those was done on EMA500).
- Research reads a 5m grid filled forward (a missing bar is O = H = L = C = previous close, volume 0). The Engine reads the bars
  that exist. Where this changes a value (top share count, forming open, own-colour bars) the parity report says so.

## Decisions

### D1. Operand `wave_measure`

`{"wave_measure": {"episode", "measure", "touch"?, "atr"?}}`. `touch` is `current` (default) or `previous` and only
`depth_share` accepts `previous`. `atr` is required by `impulse_atr` and rejected elsewhere. All values are missing where the
current touch has no valid wave, where `H ≤ 0` or where an input is not finite. Nothing after `t` is read.

| measure | value | extra missing rule | research |
|---|---|---|---|
| `impulse_atr` | `H ÷ ATR[P]`, `atr` a feature of kind `atr` or `atr_wilder` on the base timeframe | ATR not > 0 | `b3h = Hs / A48[P]`, A48 = rolling mean of TR over 48 bars = kind `atr` period 48 |
| `speed_ratio` | `(|peak_price − close[t]| ÷ (t − P + 1)) ÷ (H ÷ (P − S* + 1))` | — | `a3` |
| `duration_ratio` | `(t − P + 1) ÷ (P − S* + 1)` | — | `a4` (computed only when `Hs > 0`) |
| `efficiency_gap` | `ER(P, t) − ER(S*, P)`, `ER(a, z) = |close[z] − close[a]| ÷ Σ_{u=a+1..z} |close[u] − close[u−1]|` | `t = P`, either path sum 0 | `a5` |
| `depth_share` | `g · (peak_price − X) ÷ H`, X = lowest low (long) / highest high (short) of bars `P..t` | — | `c31` |

Here the pullback counts bar P (`t − P + 1` bars, extreme over `P..t`), as research does for A3/A4/C3.1. This differs on purpose
from `leg_mean`/`candle`/`leg_volume`, whose pullback is `[P+1, t]`.

`depth_share` with `touch: previous`: the previous touch row of the same episode with peak `P0`, `peak_price0`, `origin_price0`;
X0 = extreme of bars `P0..S*` (from the previous peak to the origin of the current wave, both inclusive), `H0 = |peak_price0 −
origin_price0|`, value `g · (peak_price0 − X0) ÷ H0`. Missing on the first touch of an episode, when `S* ≤ P0` or `H0 ≤ 0`.

**C3.2** = `ratio(left: depth_share current, right: depth_share previous, right_floor: <config, research 1e-6>)`. Research:
`c32 = c31 / v0` only when `v0 > 1e-6`; `ratio` gives the same with `right_floor`.

### D2. Operand `leg_volume`

`{"leg_volume": {"episode", "leg", "aggregate", "bars"?, "top_share"?}}`. Legs exactly as `leg_mean`: impulse `[S*, P]`,
pullback `[P+1, t]`. `bars`: `all` (default) or `own_color`. Own colour: on the impulse the bars with `close > open` (long) /
`close < open` (short); on the pullback the opposite colour. A bar with `close = open` is never own colour.
`aggregate`: `sum` or `top_mean`. `top_mean` needs `top_share` in (0, 1] and is rejected with `bars: own_color`; it is the mean
of the `k` largest volumes of the leg, `k = max(1, ceil(top_share · L))` in float64, L the number of bars of the leg (research
`np.ceil(0.1 * len(x))`, so L = 30 gives k = 4; kept for parity).
Missing where there is no valid wave, the leg is empty (`t = P` for the pullback) or a volume (or open/close for `own_color`) of
the leg is not finite. A `sum` of 0 is a value; `ratio` then makes the ratio missing when it is the denominator.

- **V1.1** = `ratio(leg_volume(pullback, sum), leg_volume(impulse, sum))` (research `v11 = dr_ / di_`, `di_ > 0`).
- **V1.2** = same with `bars: own_color` (research `v12 = wr / wi`, GV/RV by `C > O` / `C < O`).
- **V1.4** = `ratio(leg_volume(pullback, top_mean, top_share), leg_volume(impulse, top_mean, top_share))`, research 0.1.

### D3. Operand `forming_candle`

`{"forming_candle": {"timeframe", "atr", "episode"?}}`. Buckets of `timeframe` on the epoch grid (UTC days for `1d`), as the
`candle` operand. On bar `t`: `open` = the open of the first base bar of the bucket containing `t`; value
`g · (close[t] − open) ÷ ATR[k−1]`, `ATR` the `atr_wilder` feature of the same timeframe and `k−1` the last closed candle
before the bucket. Missing when that ATR is missing or not > 0. With `episode` the value is also missing where the current touch
of that episode has no valid wave (research computes D1 only for entries with a wave; without it the Engine would vote D1 on
entries research leaves silent).
**D1** = `forming_candle(1d, atr_wilder 14 on 1d, episode)` (research `d1_1d = G·(c − o_)/A`, `A = atr[kp]`, Wilder 14 seeded
with the mean of the first 14 TR). Research also requires `kp ≥ 14` (the first day with ATR is skipped): only the first two weeks
of history, reported at parity.

### D4. Identity and cost

Each operand is its own node family (`predicate.wave_measure`, `predicate.leg_volume`, `predicate.forming_candle`) with its
params, upstream the episode (when named), the base bars and the ATR feature. Candidates that differ only in a level share all
operands. `wave_measure`, `leg_volume` `sum` and `forming_candle` are O(n) from per-touch constants and prefix sums / running
extremes. `top_mean` on the impulse is computed once per touch; on the pullback it is evaluated only on bars with a valid wave
in bounded chunks, O(n · L).

### D5. Short side

All values are side-signed through `g` or through the leg colours, so a short is the mirror of a long. `duration_ratio` and the
`leg_volume` `all` values do not depend on the side.

### D6. Vote B in `weighted_vote_setup` (check, no change)

Research vote B (`vote2.py`, version v1, scheme `linear`, θ 0.75): weight `w = min(r / 0.55, 1)` per filter, variants of one
indicator merged by max (V1.x, B1 legs), sum, block at `score ≥ θ − 1e-9` or any veto; hits `x ≤ T` / `x ≥ T` inclusive; NaN
never hits. The Engine module does the same: a voter's weight is the max of its inputs, the score is the exact sum, block at
`score ≥ threshold` or any veto, levels inclusive, a missing value crosses no step. The only difference is the exact decimal
sum: weights go to the config rounded to 4 decimals. The nearest subset sum of vote B to 0.75 is 0.7582 (C3.1 + A5 + A4), so
rounding cannot move a decision; the parity task checks it on all entries.

Vote B as a config (levels and weights are the owner's numbers from research, held only in the config):

| voter | input | direction | steps (level → weight / veto) |
|---|---|---|---|
| D1 | forming_candle 1d | at_most | −0.274 → 0.8564 |
| B1 | candle ratio 15m (existing) | at_least | 1.37 → 0.6636 |
| V1 | V1.1 | at_most | 0.0574 → 0.6618; 0.0441 → veto |
| V1 | V1.2 / V1.3 (existing) / V1.4 | at_most | 0.0422 / 0.0747 / 0.084 → veto |
| A2.2 | existing | at_most | 0.158 → 0.54 |
| C3.1 | depth_share | at_least | 0.604 → 0.4109 |
| V2.2 | existing | at_least | 5.11 → 0.4109 |
| A3 | speed_ratio | at_least | 3.33 → 0.3891; 15.8 → veto |
| B3 | impulse_atr | at_most | 9.59 → 0.32; 4.65 → veto |
| A5 | efficiency_gap | at_least | 0.26 → 0.1982 |
| A4 | duration_ratio | at_least | 10.3 → 0.1491 |
| A1 | A1s (existing) | at_most | −0.0125 → veto |
| C5 | anchor_follow (existing) | at_least | 0.685 → veto |
| C3.2 | ratio of depth_share | at_least | 3.43 → veto |

threshold 0.75. The V1 inputs sit in one voter, as research merges V1.x by max; only V1.1 has a weight, so this equals separate
voters. The existing components (A1s, A2.2, B1 15m, V1.3, V2.2, C5) were checked on EMA500 only; their EMA200 values are part of
the parity task.

## Risks

- Filled grid vs real bars (Context): differences only around missing bars; quantified at parity.
- `top_mean` cost on long pullbacks: bounded chunks as in `_window_top_sum`; measured in the batch benchmark task.
