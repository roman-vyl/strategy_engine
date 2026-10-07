## Why

Canonical features describe a value at a bar (EMA, ATR, RSI, ADX/DI). None describes the geometry of the last price swing: how
long and how fast the market moved to its latest extreme, and how long and how fast it has retraced from it since. Such a ratio
cannot be composed from existing kinds and predicates, because it needs the bar positions of an extreme and of the low before
it. It is added once, as a generic feature kind usable by every predicate on any supported timeframe.

A ratio of this kind is undefined on bars where no swing can be marked. A rule of the form "allow unless the ratio is at least
X" must treat such bars as allowed, which the predicate layer cannot express today (a missing operand is always False, and
there is no negation). One explicit, opt-in option on the value predicates closes this gap.

## What Changes

- New feature kind `swing_retrace` (requestable, any timeframe, completed-bar alignment), with parameters:
  - `direction`: `up` or `down`;
  - `measure`: `bar_ratio` or `speed_ratio`;
  - `anchor`: `window` or `ema_touch`;
  - `bars`: positive integer (the window length, or the maximum age of the left edge for `ema_touch`);
  - `touch_period`: EMA period of the touch line (`ema_touch` only);
  - `stack_periods`: optional list of at least two strictly increasing EMA periods (`ema_touch` only).
- Value on a completed bar `i` of the feature's timeframe (for `up`; `down` is the mirror):
  - the left edge `L` from the anchor;
  - the extreme `P` = first bar with the highest high in `[L, i]`, the start `S` = first bar with the lowest low in `[L, P]`;
  - `impulse_bars = P − S + 1`, `retrace_bars = i − P`, `H = high[P] − low[S]`, `D = high[P] − min(low[P..i])`;
  - `bar_ratio = retrace_bars / impulse_bars`;
  - `speed_ratio = (D / retrace_bars) / (H / impulse_bars)`;
  - NaN where the swing is undefined (no left edge, `H ≤ 0`, or `retrace_bars = 0` for `speed_ratio`).
- New optional field `if_missing` on `compare`, `range` and `change`: `false` (default, today's behaviour) or `true`. With `true`,
  the predicate is True on a bar where an operand is missing or non-finite. It is not allowed on `state` or `temporal`, and not in
  the `short` override.
- Live history: `bars` plus, for `ema_touch`, the EMA convergence warm-up of the largest period used.
- Nothing changes for specs that do not use `swing_retrace` or `if_missing`: no change in values, labels, `plan_hash`, node
  identities or compute cost.

## Impact

- ADDED capability `swing-retrace-indicator-v1`.
- `pre-entry-predicates-v1`: MODIFIED `Supported predicate classes`, `Non-finite values are not satisfied`, `Side semantics`.
- `live-calculation-window-planning`: ADDED `History policy for the swing retrace feature`.
- Not modified: `ema-pullback-composite-setup-v1`, `ema-pullback-composite-phase-condition-v1`, `ema-pullback-feature-plan-v1`
  (the kind is planned like any other through the canonical feature-kind contract), `historical-managed-projection-v1`.

## Verification

- Unit tests of the kind on hand-built bars: both anchors, both measures, both directions, ties, `H ≤ 0`, `retrace_bars = 0`, no
  touch within `bars`, stack run start later than the last touch, a higher timeframe (completed bars only, no look-ahead).
- A reference test: the vectorized implementation equals a plain per-bar loop on a random walk for every parameter combination.
- `if_missing`: True on missing bars only when set, unchanged behaviour by default, rejection on `state`, `temporal`, `short`.
- History: a later-starting window gives values equal to the full window wherever both are defined.
- Gate: ruff, mypy, the full suite, `openspec validate swing-retrace-feature-v1 --strict`.
