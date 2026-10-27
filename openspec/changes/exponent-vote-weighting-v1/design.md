## Context

Research source of truth: `/mnt/project-files/ema200_calib/review/surf/w8vote/maskwin8.py` (exec chain from `review/oi/w1`:
`volspot/expvote.py` → `oi/w8/var/wkvote.py` → `d1vvote.py` → `vetoexp.py` → `bexpo.py` → `kfam.py` → `ens.py` → `research/theta7.py` …).

- Table: `e = np.where(isfinite(x), np.interp(x, grid, np.maximum(pooled, 0)), 0)`.
- Weight: `w = (np.exp(k * e) - 1) / (np.exp(k * ev) - 1)`.
- Block: `score >= θ − 1e-9 | vetoes`, θ 1.75.

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

### D4. Short operand

Features have no side. Research reads Wk as `g · body`. An input MAY name the operand of the short side:
`"short": {"operand": {"difference": {"left": {"const": 0}, "right": <1w candle_body_atr>}}}`. Long reads `operand`. Not on `count`.

### D5. Gate

D1v = today's forming 1d candle when yesterday's body ≥ 1 ATR our way and yesterday's close position ≥ 0.85 our way; else research
writes 9, whose curve value is 0 (D1v curve end −1.5 clipped). `when` = list of layer predicates (each with its `short` override);
gate closed → weight 0 and no veto; a predicate on a missing operand is False (layer rule), as research's `ok`.

### D6. Identity

The normalised setup config including `weighting`, `between`, `short`, `when` is part of the setup node identity. Specs without them keep
their identities byte for byte.

## Variant 8 config (numbers in config only)

θ 1.75. Vetoes: the nine vote-B veto voters as now (a1s ≤ −0.0125, c5 ≥ 0.685, a3 ≥ 15.8, v11 ≤ 0.0441, v12 ≤ 0.0422, v13 ≤ 0.0747,
v14 ≤ 0.084, b3h ≤ 4.65, c32 ≥ 3.43). All curve inputs: `between: "linear"`, `weighting.exponent`.

| Voter (OR = one voter, several inputs) | k | e_v | ladder (black curve) |
|---|---|---|---|
| W8_14, W8_30, W8r (each a voter; no W8_60: `bexpo.py` sets `FAM = ['W8_14', 'W8_30', 'W8r', 'W8p']`) | 0.15 | 16 | `oi/w8/var/excess_var.json` `<name>|low` |
| W8p | 0.15 | 16 | `oi/w8/research/excess.json` |
| OR(kI, O1) | 0.3 / 0.6 | 16 / 20 | `excess.json` |
| OR(W1d, W1r) | 0.3 | 16 | `excess.json` |
| W2d | 0.6 | 16 | `excess.json` |
| D1v (`when`: yesterday `candle_body_atr 1d` ≥ 1 and `candle_close_position 1d` ≥ 0.85; short overrides ≤ −1 and ≤ 0.15) | 0.2 | 8 | `excess.json` |
| Wk (`short`) | 0.2 | 10 | `excess.json` |
| vol1h low, vol1h high | 0.3 | 8 | `volspot/excess_vol.json` (slot, volume source pending) |
| OR(three EMA slopes) | 0.3 | 16 | `emaslope/excess_slope.json` |

Paths under `/mnt/project-files/ema200_calib/review/`. Premium PS_R excluded.

Research's short close position is `(H − C)/(H − L)` = `1 − (C − L)/(H − L)`, so the short gate `≥ 0.85` is `≤ 0.15` on the Engine's
side-free feature (checked in `parity_cc`, review by the thread «Компоненты голоса Б EMA200 в Engine», 2026-10-27 10:3x).
