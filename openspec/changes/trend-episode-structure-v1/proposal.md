## Why

A pullback strategy on an anchor EMA needs facts about the part of the current trend that has already happened:

- which touch of the anchor this is;
- whether price is sawing at the line or has broken through it;
- where each impulse and each pullback of the trend began and ended.

These are facts about market structure. They are not regimes of another timeframe, and they are not strategy rules.

Today the only component that tracks a trend episode is `ema_bounce_counter_setup`. It keeps the episode private, as one input to its own mask. Its touch rule, window and one-bar stack break differ from the owner-approved model (v6). No other component can read the episode, and impulses and pullbacks are not modelled at all.

This change adds a market-structure layer, beside the HTF context layer and below setups, blockers and triggers. The first and only structure in v1 is the trend episode: a causal segmentation of the trend into an episode, touch zones, impulses and pullbacks, rebuilt deterministically from candles up to the evaluated bar.

## What Changes

- New spec section `raw_spec.market_structure`: named structures, each `{"component_id": "trend_episode", ...}`. It is separate from `raw_spec.contexts`, and a structure is not a context provider.
- `TrendEpisodeProjection`, per side and per base bar, computed only from bars up to that bar:
  - Episode rule:
    - start S0 = first bar of `fast > anchor > slow` (long);
    - stack break = order violated for more than `break_bars` bars.
  - Touch rule (v6): a touch is counted only on an approach against the trend. Contacts within `window_bars` of each other extend one zone. A false break is more than `window_bars` bars wholly beyond the line. A comeback after a false break gets no number.
  - Structural ranges, each described by its start bar, end bar, bars, high, low, and whether it is final:
    - the episode;
    - touch zones `k ≥ 1`;
    - false breaks;
    - impulses `k ≥ 0`;
    - pullbacks `k ≥ 0`.
  - Current state fields: `episode_active`, `episode_id`, `bars_since_start`, `touch_number`, `phase`, `false_breaks`, `censored`, and events.
- Minimal consumer: the `state` predicate can read a structure state field, for example `touch_number < 3`, inside `composite_setup` or any other predicate host. This exercises the full path from candles through the projection to a strategy decision.
- The strategy range result carries the projection: per-side state series and a table of ranges with the bar at which each became known.
- Live history: an explicit `history_bars` plus the EMA warm-up. An episode that would start before the window is `censored` and fails closed.
- No persistent state: Research and live both rebuild the projection from candles.
- Specs without `market_structure` are unchanged: same values, labels, `plan_hash`, node identities and compute counts.

## Out of scope (next change)

- Semantic range consumption, i.e. computing existing features on structural ranges, for example ADX on `previous_impulse` versus `previous_pullback`.
- Reading range geometry in predicates.
- Range-based metrics such as ER, momentum or Fibonacci.

The projection in v1 only defines and exposes the ranges.

## Impact

- ADDED capability `trend-episode-structure-v1`.
- `pre-entry-predicates-v1`: MODIFIED `Supported predicate classes` and `Side semantics`.
- `live-calculation-window-planning`: ADDED `History policy for the trend episode structure`.
- `batch-computation-reuse`: ADDED identity and no-regression requirements.
- Not modified: `htf_context` and the context bundle, `ema_bounce_counter_setup`, triggers, exits, the managed state machine and `historical-managed-projection-v1`.

## Verification

- Hand-built bar sequences for every rule, both sides.
- Fixtures of the two owner-approved drawings with their drawn numbers.
- Truncation invariance: every value on bar `t` is unchanged when later bars are removed.
- Parity with the research reference `counter_v6.py` on BTCUSDT.P and ETHUSDT.P 5m, per bar and per range.
- End-to-end: a `composite_setup` with `touch_number < 3` gives the expected entries.
- Identity, memo and no-regression tests. Gate: ruff, mypy, the full suite, `openspec validate trend-episode-structure-v1 --strict`.
