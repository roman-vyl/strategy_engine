## Context

Research source of truth: `/mnt/project-files/ema200_calib/review/surf/w8vote/maskwin8.py` (exec chain from `review/oi/w1`:
`volspot/expvote.py` → `oi/w8/var/wkvote.py` → `d1vvote.py` → `vetoexp.py` → `bexpo.py` → `kfam.py` → `ens.py` → `research/theta7.py` …).

- Table: `e = np.where(isfinite(x), np.interp(x, grid, np.maximum(pooled, 0)), 0)`.
- Weight: `w = (np.exp(k * e) - 1) / (np.exp(k * ev) - 1)`.
- Block: `score >= θ − 1e-9 | vetoes`, θ 1.75 (owner 11:13: θ 1.5 on Engine values, see below).

Brief: `/mnt/project-files/engine-tasks/ema200/vote_v8/BRIEF.md`.

## Decisions

### D1. Two ways to weigh, chosen in the spec

The ladder stays the only table. `weighting` says what its value means:

| `weighting` | weight of the input |
|---|---|
| absent | the ladder value (today, vote B) |
| `{"exponent": {"k": k, "e_v": e_v}}` | `(exp(k·x) − 1) / (exp(k·e_v) − 1)`, `x` = ladder value |

- Computed in float64 in exactly this form (not `expm1`), as research.
- Per input: an OR voter may hold inputs with different `k`, `e_v` (kI|O1).
- Allowed only on inputs of `vote` voters, without veto steps.
- `k`, `e_v` > 0, finite. Overflow guard: `k · max(ladder values)` ≤ 700 and `k · e_v` ≤ 700.
- No cap: `x > e_v` gives `w > 1`.

### D2. Between steps: step or linear

Today (`between` `step`): an `at_most` input crosses every level ≥ value; the weight is the largest crossed. `between: "linear"`:

- the ladder is the points (level, value) sorted by level;
- the value is linear between neighbouring points, the first point's value left of them and the last point's value right of them
  (`numpy.interp`); this is the research black curve;
- `direction` is not used (the curve shape says which end is bad), veto steps are not allowed, levels need ≥ 2 points.

Check (`/mnt/project-files/engine-tasks/ema200/vote_v8/step_check/`, maskwin8.py with interpolation replaced by the step ladder): pure steps lose 50 / 51 / 38 blocked entries
(BTC / ETH / SOL) and add none; linear reproduces maskwin8 exactly.

Config writes the black curve's points with negative values already clipped to 0 (research clips nodes before interpolation). Only the
corner points are needed: points inside a flat run add nothing (121 → 18-50 points per curve, identical result, 597 points in total).

### D3. Exact score with float weights

Steps keep 9-digit exact decimals. With an exponent or linear input in the setup (their weights are floats), every voter weight is taken exactly (float64 → rational, decimal →
rational), the sum is exact, the block is `score ≥ threshold` exact. Implementation: float64 sum on every bar; bars within 1e-6 of θ
are decided again over `Fraction`. The evidence `score` is the float64 sum. Research blocks also in [θ − 1e-9, θ); parity counts such entries
(expected 0); if any, the owner sets θ in config. No tolerance in the Engine.

### D4. No trade side in the vote

The first draft let an input name a short-side operand (Wk) and a `when` gate (D1v). Removed (owner 10:36): computing the right sign is
the filter's job. The vote reads the operand value of the side as the operand gives it. Wk and D1v need operands that return their value
"our way"; until then they cannot join the variant 8 config.

### D5. Identity

The normalised setup config including `weighting` and `between` is part of the setup node identity. Specs without them keep
their identities byte for byte.

## Variant 8 config (numbers in config only)

Owner 2026-10-27 11:13: v8 is fixed on the Engine's own 5m values. The OI and slope curves were recalibrated on Engine parity values with
the same method (review thread, `/mnt/project-files/engine-tasks/ema200/vote_v8/engine_curves/`, `build.py`). θ **1.5**. Vetoes: the nine
vote-B veto voters as now (a1s ≤ −0.0125, c5 ≥ 0.685, a3 ≥ 15.8, v11 ≤ 0.0441, v12 ≤ 0.0422, v13 ≤ 0.0747, v14 ≤ 0.084, b3h ≤ 4.65,
c32 ≥ 3.43). All curve inputs: `between: "linear"`, `weighting.exponent`, the curve's points as steps with negative values clipped to 0.
Curve tails stay as they are, even where only 1-3 entries per coin are cut (owner 10:35).

| Voter (OR = one voter, several inputs) | k | e_v | ladder (black curve) |
|---|---|---|---|
| W8_14, W8_30, W8r (each a voter; no W8_60) | 0.15 | 16 | `engine_curves/oi_curves_engine5m.json` |
| W8p | 0.15 | 16 | `oi_curves_engine5m.json` |
| OR(kI, O1) | 0.3 / 0.6 | 16 / 20 | `oi_curves_engine5m.json` |
| OR(W1d, W1r) | 0.3 | 16 | `oi_curves_engine5m.json` |
| W2d | 0.6 | 16 | `oi_curves_engine5m.json` |
| D1v (`only_if` operand on teko29 7c684da) | 0.2 | 8 | `review/oi/w8/research/excess.json` `D1v` |
| Wk (`signed` operand on teko29 7c684da) | 0.2 | 10 | `review/oi/w8/research/excess.json` `Wk` |
| vol1h low, vol1h high (one operand: `rolling_sum` volume 12 ÷ (`rolling_sum` volume 5760 lag 12 ÷ 480), teko29 df26588) | 0.3 | 8 | `review/volspot/excess_vol.json` |
| OR(three EMA slopes, window ending at the evaluated bar) | 0.3 | 16 | `engine_curves/slope_curves_engine_bar.json` |

`review/` = `/mnt/project-files/ema200_calib/review/`. Premium PS_R excluded. Missing value → weight 0 for every voter (research
`np.where(isfinite(x), …, 0)`).

D1v gate in research: yesterday body ≥ 1 ATR our way and close position ≥ 0.85 our way (on a short `(H − C)/(H − L)`, i.e. ≤ 0.15 on
the side-free feature); else 9 → weight 0. Wk = `g · body` of the previous week. Both belong in their operands.
