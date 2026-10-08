## Why

A pullback strategy on an anchor EMA needs facts about the part of the current EMA-stack trend that has already happened:

- which touch of the anchor this is;
- whether a false break happened;
- where each up leg began and peaked;
- where each pullback ran to the next touch.

Today the only component that tracks such an episode is `ema_bounce_counter_setup`. It keeps the episode private, as one input to its own mask. Its rules differ from the owner-approved touch model (v6), and its legs are not modelled at all.

This change adds the EMA stack episode as a source of facts, separate from HTF contexts and below setups, blockers and triggers. A strategy reaches it through one generic query language: a scalar episode operand usable in the existing predicates.

## What Changes

- New spec section `raw_spec.ema_stack_episode`: named episodes, `{<episode_ref>: {params}}`.
  - It is not a context provider, a setup or a blocker.
- `EmaStackEpisodeProjection`, per side and per base bar, rebuilt from candles up to that bar and never persisted.
  - **Episode and touch rules (v6):**
    - an episode starts when the stack order forms and ends when the order is violated for more than `break_bars` bars;
    - a touch counts only on an approach against the trend;
    - contacts within `window_bars` of each other extend one zone;
    - more than `window_bars` bars wholly beyond the line is a false break;
    - a comeback after a false break gets no number.
  - **Entities, kept as ordered lists per episode:**
    - touch zones;
    - false breaks;
    - waves, each with its origin `S*`, its peak `P`, its up leg `S* → P` and its pullback `P → next touch`.
  - **Wave geometry, the same with or without a false break:**
    - `S*` is the lowest low from the touch that starts the interval up to the next touch;
    - `P` is the highest high after `S*` up to the next touch;
    - the order is `S* → P → next touch`.
  - Every entity carries `known_at`, the bar from which it is final. Before that bar it is forming, as of the current bar.
- New predicate operand `{"episode": {"ref", "entity", "index", "field"}}` beside `feature`, `price` and `const`.
  - It is usable in `compare` and `range`, and through `temporal`.
  - Examples: `touch_number < 3`, `up_leg[-1].range > up_leg[-3].range`, `false_break[-1].depth > 0`.
- The strategy range result carries the projection: per-side state series and the entity tables.
- Live history: an explicit `history_bars` plus the EMA warm-up. An episode that would start before the window is `censored` and fails closed.
- Specs without `ema_stack_episode` are unchanged: same values, labels, `plan_hash`, node identities and compute counts.

## Out of scope (next change)

- Semantic ranges as the domain of existing features, such as `ADX(previous up leg)`.
- Aggregates over entities, such as the average pullback depth in the episode so far. The ordered entity lists are the data these will use.
- Arithmetic or ATR-normalized comparisons in predicates.

## Impact

- ADDED capability `ema-stack-episode-v1`.
- `pre-entry-predicates-v1`: MODIFIED `Supported predicate classes` and `Side semantics`.
- `live-calculation-window-planning`: ADDED `History policy for the EMA stack episode`.
- `batch-computation-reuse`: ADDED identity and no-regression requirements.
- Not modified: `htf_context` and the context bundle, `ema_bounce_counter_setup`, triggers, exits, the managed state machine and `historical-managed-projection-v1`.

## Verification

- Hand-built bar sequences for every rule, on both sides.
- Wave geometry with and without a false break, including a peak before the false break.
- Fixtures of the two owner-approved drawings.
- Truncation invariance.
- Parity with the research reference `counter_v6.py`, rebuilt to this geometry, on BTCUSDT.P and ETHUSDT.P 5m.
- An end-to-end `composite_setup` with `touch_number < 3`.
- Identity, memo and no-regression tests. Gate: ruff, mypy, the full suite, `openspec validate ema-stack-episode-v1 --strict`.
