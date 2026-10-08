## Context

HTF contexts answer one question: how does the market look on another timeframe? The EMA stack episode answers a different one: how is the part of the current stack trend that has already happened structured?

The owner approved the v6 touch model on two drawings, and set three rules for this change:

- the episode model stores facts only: episode, touches and zones, false breaks, extrema and ranges;
- strategies reach those facts through a generic query language, not through a special field per need;
- computing features on episode ranges is the next change.

## Goals / Non-Goals

**Goals**

- A causal `EmaStackEpisodeProjection`, rebuilt from candles, holding ordered entity lists with plain geometry.
- A generic scalar episode operand for the existing predicates.

**Non-Goals**

- No metrics inside the episode: no ADX, ER, momentum, strength or ratios.
- No features computed on episode ranges, and no aggregates over entities, in v1.
- No new setup, trigger, blocker or exit. No change to `ema_bounce_counter_setup`.
- No higher-timeframe episodes and no ATR touch tolerance.

## Decisions

### D1 A section of its own

Choice: `raw_spec.ema_stack_episode` maps an `episode_ref` to its parameters.

- It is built once per evaluation into an episode bundle, beside the `ContextBundle`, from the same FeatureFrame and market arrays.
- It is never a context provider, a gate or an exit consumption.
- The name is specific on purpose. Other structures (pivots, channels, volatility regimes) will get their own sections.

### D2 Parameters

| Parameter | Value |
|---|---|
| `fast_period`, `anchor_period`, `slow_period` | Base-timeframe EMA periods. Defaults come from `anchor_stack`. Planned through the existing EMA planning. |
| `window_bars` | Quasi-simultaneity window `n`. Default 24. |
| `break_bars` | Default `window_bars`. |
| `history_bars` | Default 15000, the `ema_bounce_counter_setup` tier for anchors up to 1000. |

Unknown keys are rejected.

### D3 Touch rules (long; short is the mirror)

On bar `t` with anchor `A`:

- `above(t)` means `L > A`;
- `below(t)` means `H < A`;
- `contact(t)` means neither.

Episode:

- It starts on the first bar with `fast > anchor > slow`.
- It ends on the bar where a run without that order exceeds `break_bars`.

Phases:

| Phase | Behaviour |
|---|---|
| `away` | If `above(t-1)` and `L(t) <= A(t)`, zone `touch_number + 1` opens. Nothing else opens a zone. |
| `in_zone` | A contact or below bar sets last contact = `t`. A contact resets the below-run; a below bar increases it. A below-run greater than `window_bars` starts a false break. An above bar resets the below-run, and ends the zone when `t − last_contact > window_bars`. |
| `false_break` | The first `C > A` is the comeback: the phase becomes `away`, with no number. |

### D4 Entities and wave geometry

Zones and false breaks:

- Touch zone `k ≥ 1`:
  - range `[touch_k, last_contact_k]`;
  - `zone_low` is the lowest low inside it, `zone_high` the highest high;
  - final at `zone_end`, or at its false-break start.
- False break of zone `k`:
  - range from the first bar of its below-run to the comeback, or to the stack break;
  - `false_break_low`;
  - `depth = zone_low − false_break_low`, which may be ≤ 0;
  - `outcome` is `comeback` or `stack_break`.

Waves:

- Wave `k ≥ 1` is the move that ends at touch `k`. Its interval starts at the episode start for `k = 1`, and at `touch_{k-1}` for `k > 1`.
- The interval ends on the bar before `touch_k`.
- `S*_k` (origin) is the lowest low in the interval. Ties take the earliest bar.
- `P_k` (peak) is the highest high on `[bar(S*_k), touch_k)`. Ties take the earliest bar.
- Up leg `k` is `[bar(S*_k), bar(P_k)]`. Down leg (pullback) `k` is `[bar(P_k), touch_k]`.
- The order `S*_k ≤ P_k ≤ touch_k` holds by construction.
- The rule is the same with and without a false break.
  - After a comeback, bars before the next touch lie above the anchor. Otherwise a zone would have opened earlier.
  - So `S*` is the zone low, the false-break low, or a low on the way back, whichever is deepest.
- The origin and the zone extreme are different entities. Without a false break they usually coincide.

Forming and final:

- After `touch_{k-1}` and before `touch_k`, wave `k` is forming:
  - `S*` is the running lowest low since the interval start;
  - `P` is the running highest high after that low, and resets when a new low is made;
  - the pullback runs from `P` to the current bar.
- Wave `k` is final at `touch_k`, with `known_at = touch_k`.
- If the stack breaks first, the last wave stays forming and is never closed artificially.

Ranges:

- Every range carries `start_bar`, `end_bar`, `bars`, `high`, `low`, `range = high − low`, `final` and `known_at`.
- The short side mirrors highs and lows. `range` and `depth` are positive in the trade's favour.
- Entities are kept as ordered lists per episode, so later aggregates can read them unchanged.

### D5 State fields per bar

| field | values |
|---|---|
| `active` | 0/1 |
| `episode_id` | running id |
| `bars_since_start` | bars since the episode start |
| `touch_number` | number of the latest zone, 0 before the first |
| `in_zone`, `in_false_break`, `away` | 0/1 |
| `false_breaks` | count so far |
| `censored` | 0/1 |
| events | `episode_start`, `touch_start`, `zone_end`, `false_break_start`, `comeback`, `stack_break`, each 0/1 on its bar |

### D6 Episode operand (the query language in v1)

Shape:

```json
{"episode": {"ref": "trend", "field": "touch_number"}}
{"episode": {"ref": "trend", "entity": "up_leg", "index": -1, "field": "range"}}
```

- `entity` is omitted for state fields. Otherwise it is one of `zone`, `false_break`, `up_leg`, `down_leg`, `wave`.
- `index`:
  - `0` (alias `current`): the wave or zone of the latest touch;
  - `-1` (alias `previous`), `-2`, …: counted back from it;
  - a positive integer `k`: number `k` in the episode;
  - `forming`: the wave in progress, for `wave`, `up_leg` and `down_leg` only.
  - A `false_break` index refers to the zone it belongs to. It is missing when that zone had none.
- Fields:
  - range entities: `bars`, `high`, `low`, `range`, `start_bars_ago`, `end_bars_ago`, `final`;
  - `zone` adds `has_false_break`;
  - `false_break` adds `depth` and `outcome_comeback`;
  - `wave` gives `origin_price`, `peak_price` and `touch_price`.
- A missing value (no episode, censored, an entity not reached yet, or an index out of range) makes the predicate False.
- The value is read for the evaluated side, as with HTF regimes.
- The operand is allowed in `compare` and `range` and through `temporal`. It is rejected in `change`, and in a `short` override, which still changes only operators and bounds.

Examples:

```json
compare(episode touch_number) < const 3
range(episode touch_number, 1, 2)
compare(episode up_leg[-1].range) > episode up_leg[-3].range
compare(episode false_break[-1].depth) > const 0
```

Not in v1: `ADX(up_leg[-1])` and averages over pullbacks.

### D7 Result and identity

The strategy range result gains `ema_stack_episode`: per `episode_ref`, its params and, per side, the state series and the entity tables (`zones`, `false_breaks`, `waves` with both legs), each with `known_at`. `contexts` is unchanged.

Identity:

- One node per side: `node_spec("episode.ema_stack", version=1)`.
- Params: `window_bars`, `break_bars`, `history_bars`, side.
- Upstream: the three EMA nodes. The `episode_ref` label is not part of the identity.
- An operand node carries its `entity`, `index` and `field`.

### D8 Live history and censoring

- Required history: `history_bars` plus the EMA warm-up from the existing policy.
- An episode whose start is not visible in the evaluated range is `censored`. All its values except `active` and `censored` are missing.

### D9 Cost

- One sequential pass per side, memoized by identity, only when the section is declared.
- Operand reads are O(bars) gathers from the entity lists.
- The research reference runs a full BTC 5m history in about 0.1 s per side.

## Risks / Trade-offs

- A Python loop per bar. Mitigation: one pass per identity per batch. Time it on the full BTC range.
- Censoring hides the first episode of each live window. Mitigation: a deep default `history_bars`.

## Open Questions

- Is a zone ceiling needed? v5 had a 24-hour consolidation label. It is dropped here.
