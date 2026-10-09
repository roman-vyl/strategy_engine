# ema-stack-episode-v1 Specification

## Purpose
A causal per-side projection of the EMA stack episode (fast > anchor > slow):
episode boundaries, touch zones against the trend, false breaks with
comebacks, and waves with up and down legs, rebuilt from candles only.
A generic episode operand exposes its scalar values to predicates.
## Requirements
### Requirement: EMA stack episode section

The engine SHALL accept an optional `raw_spec.ema_stack_episode` object mapping a non-empty `episode_ref` to a parameter object.

It SHALL build every declared episode once per strategy range evaluation, into an episode bundle, from the evaluated FeatureFrame and the frame's market arrays. Building it SHALL NOT trigger a market read or an indicator calculation beyond its planned EMA columns.

An episode SHALL NOT be accepted as a context provider, by context-consumption policies or by exit consumption.

#### Scenario: Episode beside contexts

- **WHEN** a spec declares one `htf_context` context and one episode
- **THEN** both SHALL be built once per evaluation
- **AND** the context output SHALL be identical to its output without the episode.

#### Scenario: Episode used as a gate

- **WHEN** a setup's `context_consumption` names an `episode_ref`
- **THEN** static validation SHALL reject the spec.

### Requirement: Episode parameters

An episode SHALL accept only:

- `fast_period`, `anchor_period`, `slow_period`: positive integers with `fast_period < anchor_period < slow_period`, each defaulting to the spec's `anchor_stack` period of the same role;
- `window_bars`: positive integer, default 24;
- `break_bars`: positive integer, default `window_bars`;
- `history_bars`: positive integer, default 15000.

Its EMA series SHALL be planned on the base timeframe through the existing EMA planning. Any other key, an invalid value or unordered periods SHALL be rejected statically.

#### Scenario: Defaults

- **WHEN** a spec declares an episode with no parameters and `anchor_stack` periods 500, 1000 and 2000
- **THEN** the episode SHALL use those periods, `window_bars` 24, `break_bars` 24 and `history_bars` 15000.

### Requirement: Episode boundaries

For each side the engine SHALL run a separate state machine on base bars.

- The order SHALL hold on a long bar when `fast > anchor > slow`, and on a short bar when `fast < anchor < slow`.
- A bar with a missing value SHALL count as order not held.

With no episode active, the first bar where the order holds SHALL start an episode with `touch_number` 0. With an episode active, a run of more than `break_bars` consecutive bars without the order SHALL end it, with `stack_break` 1 on the bar where the run exceeds `break_bars`.

#### Scenario: Short violation keeps the episode

- **WHEN** the long order is violated for exactly `break_bars` bars and then holds again
- **THEN** the episode SHALL continue with the same `episode_id` and `touch_number`.

#### Scenario: Long violation ends the episode

- **WHEN** the long order is violated for `break_bars + 1` bars
- **THEN** `stack_break` SHALL be 1 on the last of them
- **AND** `active` SHALL be 0 from the next bar until the order holds again.

### Requirement: Touch zones against the trend

For the long side on bar `t`, with anchor value `A`:

- `above(t)` SHALL mean `low > A`;
- `below(t)` SHALL mean `high < A`;
- `contact(t)` SHALL mean neither.

The short side SHALL mirror highs and lows.

Opening a zone: when the episode is away from the anchor, a bar with `above(t-1)` and `contact(t)`, that is `low(t) <= A(t) <= high(t)`, SHALL open zone `touch_number + 1`, with `touch_start` 1. A gap from a wholly-above bar to a wholly-below bar SHALL NOT be a touch. No other bar SHALL open a zone.

Inside a zone:

- a contact bar SHALL set the last contact to `t` and reset the below-run;
- a below bar SHALL NOT be a contact. It SHALL NOT move the last contact and SHALL NOT end the zone; it SHALL only increase the below-run by 1;
- when the below-run exceeds `window_bars`, the same zone SHALL turn into a false break, with `false_break_start` 1;
- an above bar SHALL reset the below-run, and when `t − last_contact > window_bars` it SHALL end the zone, with `zone_end` 1.

There SHALL be no limit on the length of a zone.

On the bar where the stack breaks, the zone rules SHALL NOT run. An open zone or false break SHALL become final with `known_at` on that bar, and `in_zone`, `in_false_break` and `away` SHALL be 0 on it.

During a false break, the first bar with `close > A` SHALL be the comeback, with `comeback` 1. `touch_number` SHALL NOT change.

#### Scenario: Comeback is not a touch

- **WHEN** a long false break ends with a comeback and the next bars stay in contact with the anchor
- **THEN** no zone SHALL open until a bar wholly above the anchor is followed by a bar reaching it
- **AND** that bar SHALL open zone `touch_number + 1`.

#### Scenario: Gap below is not a touch

- **WHEN** the episode is away, bar `t−1` is wholly above the anchor and bar `t` is wholly below it
- **THEN** bar `t` SHALL NOT open a zone and SHALL NOT be a contact
- **AND** the next zone SHALL open only on a contact bar that follows a bar wholly above the anchor.

#### Scenario: Saw is one zone

- **WHEN** after a touch every above bar comes at most `window_bars` bars after the last contact, and every below-run lasts at most `window_bars` bars
- **THEN** all those bars SHALL belong to one zone with one number.

#### Scenario: Below bars do not extend the zone timer

- **WHEN** the last contact is on bar `c`, bars `c+1 … c+j` are wholly below the anchor with `j ≤ window_bars`, and bar `c+j+1` is wholly above it with `j + 1 > window_bars`
- **THEN** the zone SHALL end on bar `c+j+1`
- **AND** the zone's range SHALL end on bar `c`.

#### Scenario: False break then stack break

- **WHEN** a false break is followed by a stack break with no comeback
- **THEN** the episode's last `touch_number` SHALL be the number of that zone
- **AND** the false break's `outcome` SHALL be `stack_break`.

### Requirement: Zone and false-break entities

For each zone `k` the projection SHALL record:

- its range from the touch bar to the last contact;
- `zone_low` and `zone_high` over that range;
- whether it had a false break.

For a false break of zone `k` it SHALL record:

- its range from the first bar of the below-run to the comeback or the stack break;
- `false_break_low` (long; the extreme beyond the line for short);
- `depth`, equal to `zone_low − false_break_low` for long and mirrored for short;
- its `outcome`.

A zone SHALL be final from its `zone_end` or its `false_break_start`. A false break SHALL be final from its comeback or the stack break.

#### Scenario: Deep false break

- **WHEN** a long false break reaches a low below the zone's own lowest low
- **THEN** its `depth` SHALL be positive
- **AND** `zone_low` SHALL remain the lowest low of the zone's own range.

### Requirement: Wave geometry

Wave `k ≥ 1` is the move that ends at the touch of zone `k`. For the long side:

- the interval of wave `k > 1` SHALL run from the touch of zone `k−1` to the bar before the touch of zone `k`; its origin `S*_k` SHALL be the lowest low in the interval, the earliest bar on ties;
- the origin `S*_1` of wave 1 SHALL be the lower of two candidates, a tie going to the running lowest low:
  - the lowest low from the episode start bar to the bar before the touch of zone 1;
  - the low of the nearest bar left of the episode start bar whose range covers the anchor (`low ≤ anchor ≤ high` with a finite anchor), searched back without a bound; a bar wholly above or wholly below the anchor SHALL NOT be a candidate, and when no such bar exists the first candidate SHALL apply;
- the peak `P_k` SHALL be the highest high from the bar of `S*_k` to the bar before the touch of zone `k`, the earliest bar on ties; for wave 1 it MAY lie left of the episode start bar;
- up leg `k` SHALL be the range from the bar of `S*_k` to the bar of `P_k`;
- down leg `k` SHALL be the range from the bar of `P_k` to the touch bar of zone `k`.

The bars SHALL satisfy `bar(S*_k) ≤ bar(P_k) ≤ touch_k`. The same rule SHALL apply whether or not the interval contains a false break. The origin of wave 1 MAY precede the episode start bar. Only bars up to the current bar SHALL be read.

While the touch of zone `k` has not happened, wave `k` SHALL be forming:

- its origin SHALL be the running lowest low of the interval (for wave 1: the lower of that and the left contact low);
- its peak SHALL be the running highest high after that origin, reset whenever a new low is made;
- its down leg SHALL end on the current bar.

Wave `k` SHALL be final from the touch of zone `k`. A wave forming when the stack breaks SHALL stay non-final. A wave's `touch_price` SHALL be the low of the touch bar (short: the high). If touch 1 falls on the episode start bar, wave 1 SHALL NOT exist.

The short side SHALL mirror highs and lows, with leg ranges positive.

#### Scenario: Origin inside a false break

- **WHEN** after touch 2 a false break makes the lowest low of the interval and price then rallies to a peak before touch 3
- **THEN** wave 3's origin SHALL be that false-break low
- **AND** up leg 3 SHALL run from it to the peak.

#### Scenario: Peak before the false break is ignored

- **WHEN** the highest high of the interval occurs before its lowest low
- **THEN** `P_k` SHALL be the highest high after the lowest low
- **AND** `bar(S*_k) ≤ bar(P_k)` SHALL hold.

#### Scenario: Waves at the second touch

- **WHEN** zone 2 opens on bar `t`
- **THEN** wave 2 SHALL be final with `known_at` equal to `t`
- **AND** its down leg SHALL end on bar `t`.

#### Scenario: Pullback lower than every bar since the start

- **WHEN** the stack forms on bar `s`, the nearest anchor contact left of `s` is bar `j` with `low[j]` below every low since `s`, and the pullback before touch 1 makes a lower low than every bar since `s`
- **THEN** `S*_1` SHALL be bar `j`
- **AND** `P_1` SHALL be the highest high from `j` to the bar before touch 1
- **AND** up leg 1 SHALL NOT collapse to the pullback bar.

#### Scenario: Running minimum below the left contact

- **WHEN** a bar since the episode start has a lower low than the nearest left contact
- **THEN** `S*_1` SHALL be the lowest low since the episode start, as for any wave.

#### Scenario: No contact left of the start

- **WHEN** no bar left of the episode start bar covers the anchor
- **THEN** wave 1 SHALL be computed from the episode start bar only.

#### Scenario: Gap is not a contact

- **WHEN** the bars left of the start bar are wholly above or wholly below the anchor until an older contact bar
- **THEN** only that older contact bar SHALL be the candidate.

### Requirement: Range fields

Every range entity (zone, false break, up leg, down leg) SHALL carry:

- `start_bar`, `end_bar`, `bars = end_bar − start_bar + 1`;
- `high`, `low`, and `range = high − low`;
- `final` and `known_at`.

The projection SHALL keep zones, false breaks and waves as ordered lists per episode. It SHALL NOT carry any indicator value or metric computed on a range.

#### Scenario: No metric in the projection

- **WHEN** the projection is serialized
- **THEN** it SHALL contain only bar positions, prices, counts, flags and events.

### Requirement: Causal projection without persistence

Every state value and entity value on bar `t` SHALL depend only on bars `≤ t`. The projection SHALL be rebuilt from candles for every evaluation and SHALL NOT be stored between evaluations.

An episode that starts before the slow EMA's warm-up, as given by the existing per-feature policy, has elapsed from the first bar of the evaluated range SHALL be `censored`. Its values other than `active` and `censored` SHALL be missing.

#### Scenario: Truncation invariance

- **WHEN** the episode is evaluated on bars `[0, t]` and on bars `[0, t + m]`
- **THEN** every state value and every operand value on bars `≤ t` SHALL be identical in both evaluations.

### Requirement: Projection in the API result

The strategy range result SHALL carry `ema_stack_episode`. Per `episode_ref` it SHALL contain the parameters and, per side, the state series on the context time axis and the zone, false-break and wave tables with `known_at`. The `contexts` output SHALL be unchanged.

#### Scenario: Zone rows match events

- **WHEN** the result carries an episode
- **THEN** every zone row SHALL start on a bar where `touch_start` is 1 with the same `touch_number`.

### Requirement: Approved examples

The two owner-approved drawings SHALL be kept as test fixtures. The projection SHALL reproduce their touch numbers, zones, false breaks, comebacks and episode ends exactly.

#### Scenario: Comeback drawing

- **WHEN** the drawing with touches 1, 2, 3, a false break, a comeback and a later approach is evaluated
- **THEN** the later approach SHALL open zone 4 and the comeback SHALL have no number.

### Requirement: Effective episode parameters in the feature plan

When a spec declares `ema_stack_episode`, the strategy feature plan SHALL carry `episode_params_by_ref`: for each `episode_ref`, the effective parameters after defaults (`fast_period`, `anchor_period`, `slow_period`, `window_bars`, `break_bars`, `history_bars`). A spec without the section SHALL carry no such field, and its plan and `plan_hash` SHALL be unchanged.

#### Scenario: Defaults resolved

- **WHEN** a spec declares `ema_stack_episode: {trend: {}}` with an `anchor_stack` of 500, 1000 and 2000
- **THEN** `episode_params_by_ref.trend` SHALL be `{fast_period: 500, anchor_period: 1000, slow_period: 2000, window_bars: 24, break_bars: 24, history_bars: 15000}`.

### Requirement: One episode computation for every consumer

The engine SHALL have one parameter parser and one per-side projector for the EMA stack episode. Strategy evaluation and `ema-stack-episode-query-v1` SHALL both use them.

#### Scenario: No second parser

- **WHEN** the section parser and the query parser receive the same explicit parameters
- **THEN** both SHALL yield the same `EpisodeParams`.

