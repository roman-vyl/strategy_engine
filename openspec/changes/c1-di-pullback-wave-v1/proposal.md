## Why

Research metric **C1 "strength of the new pullback against the previous one"** (group C, the falling half-wave) is the full
analogue of B2 on the pullback. It compares how far the counter-trade directional index (−DI for a long, +DI for a short) rose
during the pullback of the current touch with how far it rose during the pullback of the previous touch of the same episode.
A pullback that pushes the counter-DI much harder than the last one is a violent pullback, and most entries it leads to are
stop-losses.

- **C1.1 "counter-DI rise to the extreme"**: `ΔC_n ÷ ΔC_{n−1}`, `ΔC_w = max(C over P_w … T_w) − C[P_w]`.
- **C1.2 "average counter-DI area"**: `AreaMean_n ÷ AreaMean_{n−1}`, `AreaMean_w = mean over P_w … T_w of (C[u] − C[P_w])`.

`C` is the counter-trade DI, `P_w` the peak of the wave's impulse, `T_w` the end of the wave's pullback: the evaluated bar `t` for
the current touch and the origin bar of the current touch row (the true low of the finished pullback) for the previous touch. Both ends inclusive.

Research reference (owner's Mac, `c1/`, curves https://claude.ai/artifact/QSJpcqjVexbxdFxQzDJ2jy): C1.1 cuts from below
(≤ 0.53) and C1.2 from above (≥ 2.9) on BTC EMA500; the cut pools reach 100 % stops, so C1 is a veto voter, not a stand-alone
filter. The Engine keeps both bounds nullable; the direction lives in the manifest.

The owner wants both as Engine components first (Step 1, this change). The weighted vote (C1 as one voter) is a later,
separate change.

## What Changes

Everything builds on B2 (`b2-di-wave-v1`: `touch: previous`, `by_side`, `from_start`, `right_floor`) and on the existing
`di_plus` / `di_minus` features. No new indicator kind and no new predicate class.

- **Segment end point `next_origin`**: the origin bar of the current touch row, where the previous pullback really ended.
  Allowed only as the end of a `previous` segment, `peak → next_origin`.
- **Counter-trade series** is `by_side` with the features swapped: `long = di_minus`, `short = di_plus`. No sign change.
- **C1.1** `= ratio(segment(C, peak→current, touch current, from_start, max), segment(C, peak→next_origin, touch previous, from_start, max))`,
  **C1.2** the same with `mean_per_bar`; each inside a `range` with nullable bounds, `bounds exclusive`, `empty: pass`, and
  `right_floor` 1e-6 on the ratio.
- Thresholds, grids and the veto role live in the Research manifest, not in the Engine.

Not in this change: the vote, the catalog and manifest bindings, research surfaces, deploy.
