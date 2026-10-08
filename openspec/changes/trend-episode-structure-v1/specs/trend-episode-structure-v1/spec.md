## ADDED Requirements

### Requirement: Market-structure layer

The engine SHALL accept an optional `raw_spec.market_structure` object that maps a non-empty `structure_ref` to a structure declaration. The only supported `component_id` SHALL be `trend_episode`; any other SHALL be rejected statically.

The engine SHALL build every declared structure once per strategy range evaluation, into a market-structure bundle, from the evaluated FeatureFrame and the frame's market arrays. Building a structure SHALL NOT trigger a market read or an indicator calculation beyond its planned EMA columns.

A structure SHALL NOT be a context provider. It SHALL NOT be accepted under `raw_spec.contexts`, by context-consumption policies or by exit consumption.

#### Scenario: Structure beside contexts

- **WHEN** a spec declares one `htf_context` context and one `trend_episode` structure
- **THEN** both SHALL be built once per evaluation
- **AND** the context output SHALL be identical to its output without the structure.

#### Scenario: Structure used as a gate

- **WHEN** a setup's `context_consumption` names a `structure_ref`
- **THEN** static validation SHALL reject the spec.

### Requirement: Trend episode parameters

A `trend_episode` declaration SHALL accept only:

- `fast_period`, `anchor_period`, `slow_period`: positive integers with `fast_period < anchor_period < slow_period`. Each defaults to the spec's `anchor_stack` period of the same role.
- `window_bars`: positive integer, default 24.
- `break_bars`: positive integer, default `window_bars`.
- `history_bars`: positive integer, default 15000.

The three EMA series SHALL be planned on the base timeframe through the existing EMA planning. Any other key, an invalid value or unordered periods SHALL be rejected statically.

#### Scenario: Defaults

- **WHEN** a spec declares `{"component_id": "trend_episode"}` with `anchor_stack` periods 500, 1000 and 2000
- **THEN** the structure SHALL use those periods, `window_bars` 24, `break_bars` 24 and `history_bars` 15000.

### Requirement: Episode boundaries

For each side the engine SHALL run a separate episode state machine on base bars.

The order SHALL hold on a long bar when `fast > anchor > slow`, and on a short bar when `fast < anchor < slow`. A bar with a missing value SHALL count as order not held.

With no episode active, the first bar where the order holds SHALL start an episode, with `touch_number` 0 and phase `away`. With an episode active, a run of more than `break_bars` consecutive bars without the order SHALL end it, with `stack_break` 1 on the bar where the run exceeds `break_bars`.

#### Scenario: Short violation keeps the episode

- **WHEN** the long order is violated for exactly `break_bars` bars and then holds again
- **THEN** the episode SHALL continue with the same `episode_id` and `touch_number`.

#### Scenario: Long violation ends the episode

- **WHEN** the long order is violated for `break_bars + 1` bars
- **THEN** `stack_break` SHALL be 1 on the last of them
- **AND** the phase SHALL be `none` from the next bar until the order holds again.

### Requirement: Touch zones against the trend

For the long side on bar `t`, with anchor value `A`:

- `above(t)` SHALL mean `low > A`;
- `below(t)` SHALL mean `high < A`;
- `contact(t)` SHALL mean neither.

The short side SHALL mirror highs and lows.

In phase `away`, a bar with `above(t-1)` and `low(t) <= A(t)` SHALL open touch zone `touch_number + 1`, with `touch_start` 1 and phase `in_zone`. No other bar SHALL open a zone.

In phase `in_zone`:

- a contact bar SHALL set the last contact to `t` and reset the below-run;
- a below bar SHALL set the last contact to `t` and increase the below-run by 1;
- when the below-run exceeds `window_bars`, the phase SHALL become `false_break`, with `false_break_start` 1;
- an above bar SHALL reset the below-run. When `t − last_contact > window_bars`, it SHALL end the zone, with `zone_end` 1 and phase `away`.

In phase `false_break`, the first bar with `close > A` SHALL set phase `away`, with `comeback` 1, without a new number.

#### Scenario: Comeback is not a touch

- **WHEN** a long false break ends with a comeback and the next bars stay in contact with the anchor
- **THEN** no zone SHALL open until a bar wholly above the anchor is followed by a bar reaching it
- **AND** that bar SHALL open zone `touch_number + 1`.

#### Scenario: Saw is one zone

- **WHEN** contacts, and below-runs of at most `window_bars` bars, follow a touch with gaps of at most `window_bars` bars
- **THEN** they SHALL belong to one zone with one number.

#### Scenario: False break then stack break

- **WHEN** a false break is followed by a stack break with no comeback
- **THEN** the episode's last `touch_number` SHALL be the number of that zone.

### Requirement: Structural ranges

For each side and episode, the projection SHALL define the following ranges by bar index (long; the short side mirrors highs and lows):

- touch zone `k ≥ 1`: from its touch bar to its last contact;
- false break of zone `k`: from the first bar of its below-run to its comeback, or to the stack break;
- `S_0`: the lowest low from the episode start to `max_0`;
- `S_k` for `k ≥ 1`: the lowest low of zone `k` up to its last contact;
- `max_k`: the highest high after zone `k` (after the episode start for `k = 0`) up to the bar before the touch of zone `k + 1`;
- impulse `k ≥ 0`: from the bar of `S_k` to the bar of `max_k`;
- pullback `k ≥ 0`: from the bar of `max_k` to the touch bar of zone `k + 1`.

Each range SHALL carry `start_bar`, `end_bar`, `bars`, `high`, `low`, `final` and `known_at`.

- Impulse `k` and pullback `k` SHALL be final from the touch of zone `k + 1`. Before it they SHALL be forming, with `max_k` the running highest high and the pullback ending on the current bar.
- A zone SHALL be final from its `zone_end` or its `false_break_start`.

The projection SHALL NOT carry any indicator value or metric computed on a range.

#### Scenario: Ranges at the second touch

- **WHEN** zone 2 opens on bar `t`
- **THEN** impulse 1 and pullback 1 SHALL be final with `known_at` = `t`
- **AND** pullback 1 SHALL end on bar `t`, and impulse 1 SHALL end where pullback 1 starts.

### Requirement: Causal projection without persistence

Every state value and range on bar `t` SHALL depend only on bars `≤ t`. The projection SHALL be rebuilt from candles for every evaluation and SHALL NOT be stored between evaluations.

An episode whose start lies on the first bar of the evaluated range where the order is determinable SHALL be `censored`. All its state fields except `episode_active` and `censored` SHALL be missing, and it SHALL have no ranges.

#### Scenario: Truncation invariance

- **WHEN** the structure is evaluated on bars `[0, t]` and on bars `[0, t + m]`
- **THEN** every state value on bars `≤ t` SHALL be identical
- **AND** every range with `known_at ≤ t` SHALL be identical.

### Requirement: Projection in the API result

The strategy range result SHALL carry `market_structure`: per `structure_ref`, the declaration metadata and, per side, the state series on the context time axis and the table of ranges. The `contexts` output SHALL be unchanged.

#### Scenario: Zone rows match events

- **WHEN** the result carries a trend episode
- **THEN** every touch-zone row SHALL start on a bar where `touch_start` is 1 with the same `touch_number`.

### Requirement: Approved examples

The two owner-approved drawings SHALL be kept as test fixtures. The projection SHALL reproduce their touch numbers, zones, false breaks, comebacks and episode ends exactly.

#### Scenario: Comeback drawing

- **WHEN** the drawing with touches 1, 2, 3, a false break, a comeback and a later approach is evaluated
- **THEN** the later approach SHALL open zone 4 and the comeback SHALL have no number.
