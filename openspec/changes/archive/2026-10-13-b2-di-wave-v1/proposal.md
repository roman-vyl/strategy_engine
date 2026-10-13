## Why

Research metric **B2 "strength of the new wave against the previous one"** (group B, strength of the rising half-wave) compares
how far the trade-side directional index (+DI for a long, −DI for a short) rose during the impulse of the current touch with how
far it rose during the impulse of the previous touch of the same episode. A new wave that gained much less DI than the previous
one is a weak continuation, and the entries it produces are almost only stop-losses.

- **B2.1 "DI rise to the peak"**: `ΔDI_n ÷ ΔDI_{n−1}`, `ΔDI_w = max(D over S*_w … P_w) − D[S*_w]`.
- **B2.2 "average DI area"**: `AreaMean_n ÷ AreaMean_{n−1}`, `AreaMean_w = mean over S*_w … P_w of (D[u] − D[S*_w])`.

Both cut from below (block when the value is at or under a threshold). On BTC EMA500 (W7 / LB 20 / SL 7 / TP 5.5, 427 trades,
79.4 % stops): B2.1 ≤ 0.7 cuts 33 entries, 97 % of them stops, net about 36.5k against 25.8k without a filter; B2.2 ≤ 0.8 cuts 42
entries, 93 % stops, net about 38.5k.

The owner wants both as Engine components first (Step 1, this change), read on the impulse legs of two consecutive touches of the
same EMA-stack episode. The weighted vote (B2 as one voter) is a later, separate change.

## What Changes

Everything builds on the A1/A2 blocks (`segment`, `ratio`, `range`, the EMA-stack episode) and on the existing `di_plus` /
`di_minus` features. No new indicator kind and no new predicate class.

- **Segment field `touch`** (`current` default, or `previous`): which touch row of the episode the segment's points come from.
  `previous` reads the origin and the peak of the touch before the current one, in the same episode; on the first touch of an
  episode there is none and the segment is missing.
- **Segment series `by_side`**: `{"by_side": {"long": <feature>, "short": <feature>}}`, a series that is one feature on the long
  side and another on the short side and is **not** negated on the short side. B2 uses `di_plus` for a long and `di_minus` for a
  short; a sign flip of +DI would be wrong.
- **Segment value `from_start`**: `x[u] − x[s]` per bar `u` of the window `s … e`, where `s` is the first bar of the window.
  `max`, `min`, `sum` and `mean_per_bar` aggregate it (B2.1: `max`; B2.2: `mean_per_bar`). `max`/`min` stay O(1) per bar by
  the A2 sparse table.
- **B2.1** `= ratio(segment(DI, origin→peak, touch current, from_start, max), segment(DI, origin→peak, touch previous, from_start, max))`,
  **B2.2** the same with `mean_per_bar`; each inside a `range` with nullable bounds, `bounds exclusive`, `empty: pass`. The
  ratio is missing when the previous wave's value is not greater than `right_floor` 1e-6, so those entries are not blocked.
- **Ratio field `right_floor`** (default 0): the ratio is missing when the right side is not greater than `right_floor`. B2 sets
  it to 1e-6, as the research reference does (zero and negative previous-wave values, and values too small to divide by, give an
  empty B2).
- Thresholds and grids live in the Research manifest, not in the Engine.

Not in this change: the vote, the catalog and manifest bindings, research surfaces, deploy.
