## Context

Research source of truth: `/mnt/project-files/ema200_calib/review/surf/w8vote/maskwin8.py`, which execs (run from `review/oi/w1`)
`volspot/expvote.py` → `oi/w8/var/wkvote.py` → `d1vvote.py` → `vetoexp.py` → `bexpo.py` → `kfam.py` → `ens.py` → `research/theta7.py` →
`expo7.py` …. Weight function: `w = lambda e, k, ev: (np.exp(k * e) - 1) / (np.exp(k * ev) - 1)`. Excess:
`np.where(np.isfinite(x), np.interp(x, grid, np.maximum(pooled, 0)), 0)`. Block: `score >= θ − 1e-9 | vetoes`.

Brief: `/mnt/project-files/engine-tasks/ema200/vote_v8/BRIEF.md`. Old draft `w8-curve-weight-vote-v1` (removed in ca16a6b) used for
ideas only.

## Decisions

### D1. A curve is a kind of input, not a new setup

`weighted_vote_setup` already has everything else variant 8 needs: voters, roles, vetoes, threshold, OR as max of inputs inside a voter.
A new input form keeps one vote component and lets curve voters and the nine vote-B veto voters live in one setup.

Input with `curve`:

```json
{"input_id": "w8_14", "operand": {...},
 "curve": {"grid": [0.6286, ...], "excess": [15.802, ...], "k": 0.15, "e_v": 16}}
```

- `curve` replaces `steps` and `direction`: the curve's shape already says which end is bad.
- Allowed only in voters with `role` `vote`.
- A voter MAY mix curve and step inputs; its weight is still the max.

### D2. Evaluation exactly as research

On bar `t` of a side, with operand value `x`:

1. `x` missing or non-finite → excess 0, weight 0.
2. `y_i = max(excess_i, 0)` (nodes clipped **before** interpolation, as research `np.maximum(pooled, 0)`).
3. `e = numpy.interp(x, grid, y)`: linear between nodes, `y_0` left of the grid, `y_last` right of it, the node value on a node.
4. `w = (exp(k·e) − 1) / (exp(k·e_v) − 1)` in float64, written this way (not `expm1`) to match research bit for bit.

The end nodes matter: e.g. W8_30's last node is +0.104 pp, so every entry right of its grid gets ≈ 0.0016. The Engine keeps that.

### D3. Static validation

- `grid` and `excess`: lists of the same length ≥ 2, finite numbers, not booleans; `grid` strictly increasing.
- `k` > 0 and `e_v` > 0, finite, not booleans.
- Overflow: `k · max(y)` ≤ 700 and `k · e_v` ≤ 700 (so `exp` stays finite). Variant 8 maximum is 0.6 · 26.1 ≈ 15.7.
- No precision limit on curve numbers (floats as given). Step weights keep the 9-digit decimal rule.

### D4. Exact score with float weights

Research sums floats in a fixed order and compares with `θ − 1e-9`. The Engine must not depend on voter order, and it already compares
exactly. With a curve input present:

- each curve weight is taken at the exact rational value of its float64; each step weight at its exact decimal value;
- the score is their exact rational sum; blocked when `score ≥ threshold` exactly; the trace shows the nearest float.

Without curve inputs nothing changes (integer units of 10⁻⁹). The difference from research is only for scores within 1e-9 below θ
(research blocks, the Engine does not). Parity (task 5) counts such entries; if any exist the owner decides (e.g. θ 1.749999999 in config).
No tolerance in the Engine.

### D5. Per-side operand (`short`)

Features have no side; operands such as `forming_candle` sign themselves. Research reads Wk "our way" (`g · body`). Rather than a new
negating operand, an input MAY name the short operand: `"short": {"operand": {"difference": {"left": {"const": 0}, "right": ...}}}`.
This mirrors the predicate `short` override. It is allowed on step and curve inputs; the long side reads `operand`.

### D6. Gate (`when`)

D1v in research is `D1 1d` when yesterday's body ≥ 1 ATR our way and its close position ≥ 0.85 our way, else 9 (never cut). D1v's curve
end at the high side is −1.5 → 0, so "else 9" equals "weight 0". `when` is a list of predicates of the predicate layer (with their own
`short` overrides). On a bar where any is False the input weighs 0 and does not veto; its value is still traced. A predicate with a
missing operand is False (layer rule), as research's `ok` is False on NaN.

### D7. Identity

The normalised setup config (including curve arrays as floats, `short`, `when`) is part of the setup node identity; operands keep their
own identities. Specs without the new keys keep their identities byte for byte.

## Variant 8 config (numbers come from config, not from the Engine)

Threshold 1.75. Vetoes: the nine vote-B veto voters already in the Engine (a1s ≤ −0.0125, c5 ≥ 0.685, a3 ≥ 15.8, v11 ≤ 0.0441,
v12 ≤ 0.0422, v13 ≤ 0.0747, v14 ≤ 0.084, b3h ≤ 4.65, c32 ≥ 3.43).

| Voter (OR = one voter, several inputs) | k | e_v | curve |
|---|---|---|---|
| W8_14, W8_30, W8_60, W8r (each a voter) | 0.15 | 16 | `oi/w8/var/excess_var.json` `<name>|low` |
| W8p | 0.15 | 16 | `oi/w8/research/excess.json` `W8p` |
| OR(kI, O1) | kI 0.3, O1 0.6 | kI 16, O1 20 | `excess.json` |
| OR(W1d, W1r) | 0.3 | 16 | `excess.json` |
| W2d | 0.6 | 16 | `excess.json` |
| D1v (`when`: yesterday body/close) | 0.2 | 8 | `excess.json` `D1v` |
| Wk (`short`: negated) | 0.2 | 10 | `excess.json` `Wk` |
| vol1h low, vol1h high | 0.3 | 8 | `volspot/excess_vol.json` — slot, volume source pending |
| OR(slope_ema100_R12, slope_ema50_R24, move_ema50_R24_over_impulse) | 0.3 | 16 | `emaslope/excess_slope.json` |

Premium PS_R is excluded. Paths are under `/mnt/project-files/ema200_calib/review/`.

## Risks

- Float vs exact sum at the threshold (D4) — measured in parity.
- vol1h cannot reach full parity until the volume source is decided; parity is then also run on research's mask without vol1h.
- Large configs (≈ 16 curves × 121 points × 2): fine for JSON, part of identity.
