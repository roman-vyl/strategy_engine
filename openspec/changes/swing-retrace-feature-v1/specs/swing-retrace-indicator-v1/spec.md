## ADDED Requirements

### Requirement: Swing retrace kind

The canonical feature-kind contract SHALL contain a requestable kind
`swing_retrace` with no `source` and these parameters:

- `direction`: `up` or `down`;
- `measure`: `bar_ratio` or `speed_ratio`;
- `anchor`: `window` or `ema_touch`;
- `bars`: a positive integer;
- `touch_period`: a positive integer, required with `ema_touch` and
  rejected with `window`;
- `stack_periods`: an optional list of at least two strictly increasing
  positive integers, allowed only with `ema_touch`.

Any other parameter, value or combination SHALL be rejected before
market data is loaded. Every parameter SHALL be part of the identity.

#### Scenario: Window anchor with a touch period is rejected

- **WHEN** a feature has `anchor: window` and `touch_period` 20
- **THEN** validation SHALL reject it.

#### Scenario: Distinct identities

- **WHEN** two features differ only in `measure`
- **THEN** their identities and labels SHALL differ.

### Requirement: Left edge

At a completed bar `i` of the feature's timeframe the left edge `L`
SHALL be:

- for `window`: `i − bars`, undefined while `i < bars`;
- for `ema_touch`: the later of
  - the last bar `j ≤ i` where `EMA(touch_period)` is finite and the bar
    touches it (`low ≤ EMA` for `up`, `high ≥ EMA` for `down`), and
  - when `stack_periods` is given and their EMAs are in strict order at
    `i` (each EMA above the EMA of the next larger period for `up`,
    below it for `down`),
    the first bar of the uninterrupted run of that order ending at `i`;

  considering only those that exist; undefined when neither exists or
  when `L < i − bars`.

#### Scenario: Stack formed after the last touch

- **WHEN** the last touch is at bar 10 and the stack order has held
  without interruption from bar 14 to `i`
- **THEN** `L` SHALL be 14.

#### Scenario: Touch too old

- **WHEN** no touch and no stack run start lies in `[i − bars, i]`
- **THEN** the value at `i` SHALL be undefined.

### Requirement: Swing measures

For `up`, on `[L, i]`:

- `P` SHALL be the first bar with the maximum `high` in `[L, i]`;
- `S` SHALL be the first bar with the minimum `low` in `[L, P]`;
- `H = high[P] − low[S]`, `D = high[P] − min(low[P..i])`;
- `impulse_bars = P − S + 1`, `retrace_bars = i − P`.

`bar_ratio` SHALL be `retrace_bars / impulse_bars`. `speed_ratio` SHALL
be `(D / retrace_bars) / (H / impulse_bars)`. The value SHALL be
undefined when `L` is undefined, when `H ≤ 0`, or, for `speed_ratio`,
when `retrace_bars = 0`. For `down` the same definitions SHALL apply
with `high` replaced by `−low` and `low` by `−high`. Undefined values
SHALL be NaN.

#### Scenario: Short impulse, long retrace

- **WHEN** `S` and `P` lie in adjacent bars and `i = P + 9`
- **THEN** `bar_ratio` SHALL be 4.5.

#### Scenario: Extreme on the current bar

- **WHEN** `P = i`
- **THEN** `bar_ratio` SHALL be 0 and `speed_ratio` SHALL be undefined.

#### Scenario: Ties

- **WHEN** two bars share the maximum high
- **THEN** `P` SHALL be the earlier one.

### Requirement: Completed bars only

A `swing_retrace` value on a higher timeframe SHALL be computed from
that timeframe's completed bars and SHALL become visible on the base
grid through the canonical completed-bar alignment. No base-bar or
partial-bucket data SHALL enter it.

#### Scenario: Bucket in progress

- **WHEN** a base bar lies inside an incomplete 4h bucket
- **THEN** the aligned value SHALL equal the value of the last
  completed 4h bar.

### Requirement: Compute cost and reuse

The kind SHALL be computed only for specs that request it, once per
identity per evaluation context, in O(n log n) time or better on the
number of bars of its own timeframe. EMAs it uses internally SHALL use
the canonical EMA math and SHALL NOT add plan columns. Specs that do
not request it SHALL keep their values, labels, `plan_hash`, node
identities and compute counts.

#### Scenario: Spec without the kind

- **WHEN** a spec without `swing_retrace` is planned and evaluated
- **THEN** its plan and outputs SHALL equal those before this change.
