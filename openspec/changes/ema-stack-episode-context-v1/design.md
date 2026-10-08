## Context

`raw_spec.contexts` holds named context providers. Today the only provider is `htf_context`: a stateless up/down/neutral classification of an EMA stack. It is built once per evaluation in `build_context_bundle`, and it is read by context-consumption gates, exits and the `state` predicate.

`ema_bounce_counter_setup` (`setups.py::_ema_bounce_counter`) tracks a trend episode internally, but its state is private. Its touch rule is a range cross from either side with a fixed window, and its stack break is one bar.

The owner approved a new touch model (v6) on two drawn examples. The model must become part of the strategy information: at any bar, the evaluator must be able to ask the episode what has happened so far, without knowing future bars.

## Goals / Non-Goals

**Goals**

- One causal, per-bar description of the EMA stack episode, its touch zones and its waves, readable by every predicate.
- Leg geometry for every wave, as a base that later leg metrics extend without changing the model.

**Non-Goals**

- No change to `ema_bounce_counter_setup` or to any existing component.
- No new trigger, setup, blocker or exit. Entry on "start of zone k" is expressed with existing composition, as shown below. Exits on a stack break are a later change.
- No leg metrics beyond geometry: prices, bars and heights.
- No higher-timeframe episodes: the episode runs on the base timeframe in v1.
- No ATR tolerance for touches.

## Decisions

### D1 The episode is a context provider

Choice: a provider `{"component_id": "ema_stack_episode", ...}` under `raw_spec.contexts`.

- It is built in `build_context_bundle` from the FeatureFrame, once per evaluation, like `htf_context`.
- It is not a trigger, setup, blocker or filter. It describes state; consumers decide what to do with it.

Why: the context layer already means "strategy-level state, built once, read by several consumers". A trigger would fix one use. A feature kind would have to be side-free and scalar, but the episode is side-specific and multi-field.

### D2 Parameters

- `fast_period`, `anchor_period`, `slow_period`: EMA periods on the base timeframe.
  - Default: the spec's `anchor_stack` periods.
  - The EMA columns are planned through the existing EMA planning, so a stack shared with `anchor_stack` is computed once.
- `window_bars`: the quasi-simultaneity window `n`. Positive integer, default 24.
- `break_bars`: positive integer, default `window_bars`. The stack is broken after more than `break_bars` consecutive bars without the side's order.
- `history_bars`: positive integer, the live window depth (D8). Default 15000, the `ema_bounce_counter_setup` tier for anchor periods up to 1000.

Unknown keys are rejected.

### D3 Rules (long; short is the mirror)

Notation for bar `t`: `A` is the anchor EMA; `H`, `L`, `C` are high, low and close.

- `above(t)`: `L > A`.
- `below(t)`: `H < A`.
- `contact(t)`: neither above nor below.

Episode:

- With no episode active, the first bar with `fast > anchor > slow` is S0.
  - It opens episode `episode_id + 1` with `touch_number = 0` and phase `away`.
- With an episode active, a run of more than `break_bars` consecutive bars without that order ends it on the bar where the run exceeds `break_bars` (`episode_break` event).
  - Bars inside a shorter run continue the episode.
- After a break, a new S0 needs the order again.

Phases inside an episode:

- `away`
  - If `above(t-1)` and `L(t) <= A(t)`: touch.
    - `touch_number += 1`; phase becomes `in_zone`; `touch_start` event.
    - The zone's last-contact bar is `t`. Its deepest low starts at `L(t)`.
  - Any other bar, including a bar in contact right after a comeback, does nothing.
- `in_zone`
  - `contact(t)`: last contact = `t`; the below-run resets.
  - `below(t)`: last contact = `t`; the below-run grows by one.
    - When the below-run exceeds `window_bars`, the phase becomes `false_break` (`false_break` event at that bar).
  - `above(t)`: the below-run resets.
    - If `t - last_contact > window_bars`, the zone ends and the phase becomes `away` (`zone_end` event).
  - The deepest low is updated on every zone bar.
- `false_break`
  - The deepest low keeps updating.
  - The first bar with `C > A` ends the false break: phase `away`, `comeback` event, no number.

Long and short are separate episodes: each side runs its own state machine on its own order.

### D4 Waves and legs

Wave `k` (k ≥ 1) is the move that ends at touch `k`.

- `S_0`: the lowest low in `[S0, P_1]`. It is known once `P_1` is fixed, at touch 1.
- `P_k`: the highest high from the end of zone `k-1` to the bar before touch `k`. For `k = 1` the range starts at S0.
  - It is known at `touch_start` of zone `k`.
- `S_k`: the deepest low of zone `k`, from its touch to its last contact.
  - False-break bars are not part of it. The false break's own lowest low is the wave field `false_break_low`.
  - `S_k` is a running value while zone `k` is open. It is final at `zone_end`, or at `false_break_start`.
- Up leg `k`: `S_{k-1} → P_k`.
- Down leg `k`: `P_k → S_k`.

The forming wave is the move after the last zone has ended:

- forming up leg: `S_last` to the running maximum;
- forming down leg: from that maximum to the lowest low since it.

The short side mirrors highs and lows. Heights are always positive in the trade's favour.

### D5 Fields

All fields are numbers on the base timeline, per side.

- NaN where not applicable: no episode, the wave not reached yet, or a censored episode (D8).
- Booleans are 0/1.

Episode fields (no `wave` selector):

| field | meaning |
|---|---|
| `episode_active` | 1 inside an episode |
| `episode_id` | running id |
| `bars_since_s0` | bars since S0 |
| `touch_number` | number of the latest zone, 0 before the first touch |
| `phase` | 0 `none`, 1 `away`, 2 `in_zone`, 3 `false_break` |
| `in_zone`, `in_false_break` | 0/1 shortcuts for the phase |
| `touch_start`, `zone_end`, `false_break_start`, `comeback`, `episode_start`, `episode_break` | 0/1 events on their bar |
| `bars_since_touch` | bars since the latest `touch_start` |
| `zone_bars` | bars in the current zone so far, false break included |
| `false_breaks` | false breaks so far in the episode |

Wave fields, with `wave` set to `current` (zone `touch_number`), `previous` (`touch_number - 1`), `forming`, or an integer `k ≥ 1`:

- `s_start_price`, `p_price`, `s_price`;
- `up_height`, `up_bars`, `up_pct`;
- `down_depth`, `down_bars`, `down_pct`;
- `retracement` = `down_depth / up_height`;
- `false_break_low` (NaN when wave `k` had no false break);
- `final` (1 when `S_k` is final).

On bar `t` every value is as known on bar `t`.

Later leg metrics are added as new wave fields. Each needs one new row in this table and a tested formula; the model does not change.

### D6 Episode operand

Shape: `{"episode": {"context_ref": <ref>, "field": <name>, "wave": <selector>}}`.

- `wave` is required for wave fields and rejected for episode fields.
- The operand is allowed in `compare` and in `range`, on either side and against a feature, a price or a constant. Through those it is also allowed in `temporal`.
- It is rejected in `change`, and in a `short` override of `compare` or `range`; that override still overrides operators and bounds only.
- The value is read for the consumer's side, so the same predicate reads the long episode for long and the short episode for short.
- A `state` predicate or a context-consumption policy that points at an `ema_stack_episode` context is rejected statically.

Example, "enter only on the first or second touch, while the zone is fresh": in a `composite_setup`, require `range(touch_number, 1, 2)` and `compare(bars_since_touch <= 3)`.

### D7 API result and identity

- `ContextOutput` gains an optional `fields` map and a per-episode `zones` table: one row per zone with `k`, start, end, kind (`zone`, `false_break`), `S`, `P` and legs.
  - `htf_context` output is unchanged.
- Node identity: `node_spec("context.ema_stack_episode", version=1)`.
  - Params: `window_bars`, `break_bars`, `history_bars`, side.
  - Upstream: the fast, anchor and slow EMA nodes.
  - Candidates that share the stack and the params share one computation.

### D8 Live history and censoring

- Required history: `history_bars` plus the warm-up of the three EMAs, counted by the existing per-feature policy.
- An episode whose S0 would lie before the window cannot be told apart from one that starts on the first bar where the order holds. Such an episode is flagged `censored = 1`, and all its fields except `episode_active` and `censored` are NaN. This makes it fail closed.
- Historical ranges start at the dataset start, where the same rule applies.

### D9 Cost

- One sequential pass per side over the base bars: two passes over about 685k bars of BTCUSDT.P 5m.
- It is memoized by identity and computed only when an `ema_stack_episode` context is declared.
- Specs without it pay nothing.

## Risks / Trade-offs

- A Python loop over every bar. Mitigation: one pass per identity per batch, shared by all cells. Measure on the full BTC range and report.
- Censoring hides the first episode of every live window. Mitigation: a deep default `history_bars`.

## Open Questions

1. Should the next up leg start from `S_k` (here, matching the research reference `counter_v6.py`) or from the false-break low when it is deeper?
2. Is a zone ceiling needed? In v5, a zone longer than 24h of sawing was labelled consolidation. It is dropped here.
