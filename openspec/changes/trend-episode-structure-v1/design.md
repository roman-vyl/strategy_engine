## Context

`raw_spec.contexts` holds `htf_context` providers. They classify an EMA stack as up, down or neutral, and gates, exits and `state` predicates read that classification. The question they answer is: how does the market look on another timeframe, relative to this bar?

The trend episode answers a different question: how is the part of the current trend that has already happened structured? The owner approved the v6 touch model on two drawings. The structure must also become the source of semantic ranges, impulses and pullbacks, on which later changes compute existing features.

## Goals / Non-Goals

**Goals**

- A market-structure layer, separate from contexts, holding a causal `TrendEpisodeProjection`.
- Structural ranges with plain geometry only: start, end, bars, high, low, final.
- One end-to-end consumer: `state` predicates on structure state fields.

**Non-Goals**

- No metrics in the structure. ADX, ER, momentum and ratios belong to features and predicates, never to the episode.
- No range consumption by features in v1.
- No new setup, trigger, blocker or exit. No change to `ema_bounce_counter_setup`.
- No higher-timeframe episodes and no ATR touch tolerance.

## Decisions

### D1 A market-structure layer, not a context

Choice: `raw_spec.market_structure` maps a `structure_ref` to `{"component_id": "trend_episode", ...}`.

- It is built once per evaluation into a `MarketStructureBundle`, next to the `ContextBundle` and from the same FeatureFrame and market arrays.
- Setups, blockers, triggers and exits are consumers. The structure never gates by itself.

Why: the structure is a source of facts and ranges. Making it a blocker or a setup would make the source also its own consumer. Making it a kind of `htf_context` would mix two different questions.

### D2 Parameters

- `fast_period`, `anchor_period`, `slow_period`: EMA periods on the base timeframe. They default to the spec's `anchor_stack`, and are planned through the existing EMA planning, so a shared stack is computed once.
- `window_bars`: quasi-simultaneity window `n`. Default 24.
- `break_bars`: default `window_bars`.
- `history_bars`: live window depth. Default 15000, the `ema_bounce_counter_setup` tier for anchors up to 1000.

Unknown keys are rejected.

### D3 Segmentation rules (long; short is the mirror)

On bar `t`, with anchor `A`:

- `above(t)` means `L > A`;
- `below(t)` means `H < A`;
- `contact(t)` means neither.

Episode:

- With no episode, the first bar with `fast > anchor > slow` is the episode start (S0).
- An episode ends on the bar where a run of bars without that order exceeds `break_bars` (`stack_break` event).

Phases:

- `away`: `above(t-1)` and `L(t) <= A(t)` opens touch zone `touch_number + 1`, and the phase becomes `in_zone`. Nothing else opens a zone.
- `in_zone`:
  - a contact sets last contact = `t` and resets the below-run;
  - a bar below sets last contact = `t` and increases the below-run;
  - a below-run greater than `window_bars` starts a false break (phase `false_break`);
  - an above bar resets the below-run, and ends the zone (phase `away`) when `t − last_contact > window_bars`.
- `false_break`: the first bar with `C > A` is the comeback. The phase becomes `away` and gets no number.

Long and short run separate state machines.

### D4 Ranges and numbering

Zones:

- Touch zone `k ≥ 1`: `[touch_k, last_contact_k]`.
  - It is final at `zone_end`, or at the start of its false break.
- False break of zone `k`: `[first bar of the below-run, comeback bar]`.
  - It is final at the comeback.
  - If the stack breaks instead, it is final at `stack_break`.

Anchor points of the impulses:

- `S_0` is the lowest low in `[episode start, max_0]`.
- `S_k` for `k ≥ 1` is the lowest low of zone `k`, from its touch to its last contact.
- `max_k` is the highest high after zone `k` (after the episode start for `k = 0`), up to the bar before `touch_{k+1}`.

Impulses and pullbacks:

- Impulse `k ≥ 0`: `[bar(S_k), bar(max_k)]`.
- Pullback `k ≥ 0`: `[bar(max_k), touch_{k+1}]`.
- While no zone `k+1` exists, impulse `k` and pullback `k` are forming:
  - `max_k` is the running highest high;
  - the pullback runs from it to the current bar.
- Both become final at `touch_{k+1}`.

At touch zone #2 this gives:

| Owner's name | Range |
|---|---|
| `previous_impulse` | impulse 1 |
| `previous_pullback` | pullback 1 |
| `current_zone` | zone 2 |

The short side mirrors highs and lows.

Every range records `start_bar`, `end_bar`, `bars`, `high`, `low`, `final`, and `known_at`, the bar from which it is final.

### D5 Projection and state fields

`TrendEpisodeProjection` per side holds:

- the per-bar state series;
- the range table.

State fields per bar:

| field | values |
|---|---|
| `episode_active` | 0/1 |
| `episode_id` | integer, 0 outside episodes |
| `bars_since_start` | bars since S0 |
| `touch_number` | number of the latest zone, 0 before the first touch |
| `phase` | `none`, `away`, `in_zone`, `false_break` |
| `false_breaks` | count in the episode |
| `censored` | 0/1 |
| events | `episode_start`, `touch_start`, `zone_end`, `false_break_start`, `comeback`, `stack_break`, each 0/1 on its bar |

A value on bar `t` uses bars `≤ t` only. Fields of a censored episode, other than `episode_active` and `censored`, are missing.

The projection is never stored between evaluations. Research and live rebuild it from candles. Live gets bounded history (D8).

### D6 Consumer: structure state predicates

The `state` class gains a second form:

```json
{"kind": "state", "structure_ref": "trend", "field": "touch_number", "op": "<", "value": 3}
{"kind": "state", "structure_ref": "trend", "field": "phase", "in": ["in_zone"]}
```

- Numeric fields take `op` (`<`, `<=`, `>`, `>=`) and a finite `value`.
- Integer and enumerated fields may instead take `in`, a non-empty set. For `touch_number` this is set membership on integers, not float equality.
- The value is read for the evaluated side, because the projection exists per side. This is the same as `htf_context` regimes.
- A missing or censored value is False.
- The existing `context_ref` form is unchanged.
- The structure form is allowed wherever `state` is allowed, including `temporal`.

Example, "only the first two touches":

```json
composite_setup {require: [state(trend.touch_number, in [1, 2])]}
```

### D7 Result and identity

The strategy range result gains `market_structure`: per `structure_ref`, the provider metadata and, per side, the state series and the range table. `contexts` output is unchanged.

Identity:

- `node_spec("structure.trend_episode", version=1)`.
- Params: `window_bars`, `break_bars`, `history_bars`, side.
- Upstream: the three EMA nodes.
- Structure-state predicate nodes carry the field and the operator or set, with the structure node upstream.

### D8 Live history and censoring

- Required history: `history_bars` plus the EMA warm-up from the existing per-feature policy.
- An episode whose start cannot be seen inside the evaluated range is `censored` and fails closed.

### D9 Cost

- One sequential pass per side, memoized by identity, built only when `market_structure` is declared.
- The research reference does a full BTC 5m history in about 0.1 s per side.

## Risks / Trade-offs

- A Python loop per bar. Mitigation: one pass per identity per batch. Time it on the full BTC range.
- Censoring hides the first episode of each live window. Mitigation: a deep default `history_bars`.

## Open Questions

1. Should impulse `k+1` start at `S_k`, as here and in the reference, or at the false-break low when it is deeper?
2. Is a zone ceiling needed? v5 had a 24-hour consolidation label. It is dropped here.
