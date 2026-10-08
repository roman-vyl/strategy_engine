## ADDED Requirements

### Requirement: EMA stack episode provider

The engine SHALL support a context provider with `component_id` `ema_stack_episode` under `raw_spec.contexts`.

The provider SHALL accept only:

- `fast_period`, `anchor_period`, `slow_period`: positive integers with `fast_period < anchor_period < slow_period`. Each defaults to the spec's `anchor_stack` period of the same role.
- `window_bars`: positive integer, default 24.
- `break_bars`: positive integer, default `window_bars`.
- `history_bars`: positive integer, default 15000.

Any other key, a non-integer or non-positive value, or an unordered set of periods SHALL be rejected statically.

The provider's EMA series SHALL be planned on the base timeframe through the existing EMA planning.

#### Scenario: Defaults from the anchor stack

- **WHEN** a spec declares `{"component_id": "ema_stack_episode"}` with no parameters
- **AND** its `anchor_stack` periods are 500, 1000 and 2000
- **THEN** the provider SHALL use those periods, `window_bars` 24, `break_bars` 24 and `history_bars` 15000.

#### Scenario: Unknown key is rejected

- **WHEN** the provider carries a key outside the list above
- **THEN** static validation SHALL reject the spec.

### Requirement: Episode boundaries

For each side the engine SHALL run a separate episode state machine on base bars.

For the long side, the order holds on a bar when `fast > anchor > slow`. For the short side it holds when `fast < anchor < slow`. A bar where any of the three is missing SHALL count as order not held.

With no episode active, the first bar where the order holds SHALL be S0. It SHALL open a new episode with `touch_number` 0 and phase `away`.

With an episode active, a run of more than `break_bars` consecutive bars without the order SHALL end the episode on the bar where the run exceeds `break_bars`. A shorter run SHALL NOT end it.

#### Scenario: Short violation keeps the episode

- **WHEN** the long order is violated for exactly `break_bars` consecutive bars and then holds again
- **THEN** the episode SHALL continue with the same `episode_id` and `touch_number`.

#### Scenario: Long violation ends the episode

- **WHEN** the long order is violated for `break_bars + 1` consecutive bars
- **THEN** `episode_break` SHALL be 1 on the last of those bars
- **AND** from the next bar the side SHALL have phase `none` until the order holds again.

### Requirement: Touch counting against the trend

For the long side, on bar `t` with anchor value `A`:

- `above(t)` SHALL mean `low > A`;
- `below(t)` SHALL mean `high < A`;
- `contact(t)` SHALL mean neither.

The short side SHALL mirror highs and lows.

In phase `away`, a bar with `above(t-1)` and `low(t) <= A(t)` SHALL open a touch: `touch_number` increases by 1, phase becomes `in_zone`, and `touch_start` is 1 on that bar. No other bar SHALL open a touch.

#### Scenario: Approach from above opens a touch

- **WHEN** a long episode is `away`, bar `t-1` lies wholly above the anchor, and bar `t` reaches it
- **THEN** bar `t` SHALL be `touch_start` with the next `touch_number`.

#### Scenario: Comeback from below does not open a touch

- **WHEN** a long episode is `away` right after a comeback, and the next bars stay in contact with the anchor
- **THEN** no touch SHALL be opened until a bar wholly above the anchor is followed by a bar reaching it.

### Requirement: Zone extension, end and false break

In phase `in_zone`:

- a contact bar SHALL set the zone's last contact to `t` and reset the below-run;
- a bar wholly beyond the anchor SHALL set the last contact to `t` and increase the below-run by 1;
- when the below-run exceeds `window_bars`, the phase SHALL become `false_break`, with `false_break_start` 1 on that bar;
- a bar wholly on the trend side SHALL reset the below-run. If it is more than `window_bars` bars after the last contact, the zone SHALL end with `zone_end` 1 on that bar and phase `away`.

In phase `false_break`, the first bar that closes back on the trend side of the anchor SHALL set phase `away` with `comeback` 1. `touch_number` SHALL NOT change.

#### Scenario: Saw extends the zone under one number

- **WHEN** after a touch, contacts and dips wholly beyond the line of at most `window_bars` bars follow each other with gaps of at most `window_bars` bars
- **THEN** the zone SHALL stay open under the same `touch_number`.

#### Scenario: False break and comeback

- **WHEN** price stays wholly beyond the anchor for `window_bars + 1` bars and then closes back on the trend side
- **THEN** `false_break_start` SHALL be 1 on the bar where the run exceeds `window_bars`
- **AND** `comeback` SHALL be 1 on the closing-back bar
- **AND** the next touch SHALL take the number `touch_number + 1` only on the next approach from the trend side.

#### Scenario: False break and stack break

- **WHEN** a false break is followed by an episode break with no comeback
- **THEN** the episode's last `touch_number` SHALL equal the number of the zone that broke.

### Requirement: Waves and legs

For wave `k ≥ 1` of a long episode:

- `P_k` SHALL be the highest high from the bar after the end of zone `k-1` up to the bar before touch `k`. For `k = 1` the range starts at S0.
- `S_0` SHALL be the lowest low in `[S0, P_1]`.
- `S_k` SHALL be the lowest low of zone `k`, from its touch to its last contact before any false break.
- Up leg `k` SHALL run from `S_{k-1}` to `P_k`; down leg `k` from `P_k` to `S_k`.

For the forming wave after the end of the last zone:

- its up leg SHALL run from the last `S` to the running highest high;
- its down leg SHALL run from that high to the lowest low since it.

The short side SHALL mirror highs and lows. Heights and depths SHALL be positive.

#### Scenario: Legs of a completed wave

- **WHEN** zone 2 has ended
- **THEN** on every later bar of the episode, the wave fields for `wave` 2 SHALL be constant
- **AND** `up_height` SHALL equal `p_price − s_start_price` and `down_depth` SHALL equal `p_price − s_price` for the long side.

### Requirement: Per-bar fields

The provider SHALL expose, per side and per base bar, the episode fields and wave fields listed in the design.

- Every value on bar `t` SHALL be computed from bars `≤ t` only.
- Booleans SHALL be 0 or 1.
- A field that does not apply on a bar SHALL be NaN. This covers no episode, a wave not reached yet, and a censored episode.

#### Scenario: Causality

- **WHEN** the provider is evaluated on bars `[0, t]` and on bars `[0, t + m]`
- **THEN** every field on every bar `≤ t` SHALL be identical in both evaluations.

#### Scenario: Wave not reached

- **WHEN** `touch_number` is 2 on bar `t`
- **THEN** every wave field for `wave` 3 SHALL be NaN on bar `t`.

### Requirement: Censored episodes

An episode whose S0 is the first bar of the evaluated range where the side's order is determinable SHALL be marked `censored` 1. Every field of a censored episode other than `episode_active` and `censored` SHALL be NaN.

#### Scenario: Order already holds at the window start

- **WHEN** the long order holds on the first evaluated bar
- **THEN** that episode SHALL be censored until it ends.

### Requirement: Approved examples

The two owner-approved drawn examples SHALL be kept as test fixtures. On them, the engine SHALL produce exactly the drawn touch numbers, zones, false breaks, comebacks and episode ends.

#### Scenario: Comeback example

- **WHEN** the fixture with touches 1, 2, 3, a false break, a comeback and a later approach is evaluated
- **THEN** the later approach SHALL be touch 4 and the comeback SHALL have no number.
