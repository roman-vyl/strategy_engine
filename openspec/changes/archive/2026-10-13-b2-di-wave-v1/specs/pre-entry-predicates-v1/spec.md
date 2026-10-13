## ADDED Requirements

### Requirement: Segment touch selection

A segment MAY carry `touch`, `current` (default) or `previous`. With `previous` the points of the segment SHALL be read from the
touch row before the current touch row of the same episode. With `previous` the segment SHALL be `origin → peak`, other pairs
SHALL be rejected, and it SHALL be missing on a bar whose current touch is the first of its episode. A touch of an earlier
episode SHALL NOT be read.

#### Scenario: First touch

- **WHEN** a `previous` segment is evaluated on a bar of the first touch of an episode
- **THEN** its value SHALL be missing
- **AND** a `range` over a ratio of it with `empty: pass` SHALL not block the bar.

#### Scenario: Previous pair rejected

- **WHEN** a `previous` segment is `peak → current` or `origin → current`
- **THEN** static validation SHALL reject the spec.

### Requirement: Previous touch points

For a bar `t` with current touch row `r` and `touch_number ≥ 2` in the episode, a `previous` segment SHALL use the origin bar
and the peak bar of row `r − 1`, both ends inclusive. Only bars up to the peak SHALL be read, so no bar after `t` is read.

#### Scenario: Second touch

- **WHEN** the current touch is the second of its episode
- **THEN** a `previous` segment SHALL span the origin and peak of the first touch.

### Requirement: Segment series by side

The `of` field of a segment MAY be `{"by_side": {"long", "short"}}` with exactly those two feature references, both on the base
timeframe. The evaluated side SHALL read its own feature. A `by_side` series SHALL NOT be negated on the short side; a single
feature or a difference SHALL be negated as before. `negate` SHALL keep its meaning.

#### Scenario: Directional index by side

- **WHEN** `of` is `by_side` with `di_plus` for long and `di_minus` for short and the evaluated side is short
- **THEN** the series SHALL be the `di_minus` values, not negated.

#### Scenario: Malformed by_side

- **WHEN** `by_side` lacks `long` or `short`, has another key, or a feature is not on the base timeframe
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment value from start

`value: from_start` SHALL read `x[u] − x[s]` for `u = s … e`, `s` being the first bar of the window. It SHALL be allowed with
`sum`, `mean_per_bar`, `max` and `min`, and SHALL be rejected with `abs_sum`, `top_abs_sum` and `top_abs_share`. The value
SHALL be missing when any `x[s … e]` is not finite.

#### Scenario: Rise to the peak

- **WHEN** a segment is `origin → peak`, `from_start`, `max` over a series `D`
- **THEN** its value SHALL be `max(D[S* … P]) − D[S*]`.

#### Scenario: Average area

- **WHEN** a segment is `origin → peak`, `from_start`, `mean_per_bar` over a series `D`
- **THEN** its value SHALL be `mean(D[S* … P]) − D[S*]`.

#### Scenario: One-bar window

- **WHEN** the window has one bar
- **THEN** every `from_start` aggregate SHALL be 0 (`sum`, `mean_per_bar`, `max`, `min`).

### Requirement: Ratio denominator floor

A ratio MAY carry `right_floor`, a finite number, default 0. The ratio SHALL be missing when the right side is not greater than
`right_floor`. A non-finite or non-numeric `right_floor` SHALL be rejected.

#### Scenario: Tiny positive denominator

- **WHEN** `right_floor` is 1e-6 and the right side is 1e-7
- **THEN** the ratio SHALL be missing.

### Requirement: Directional index wave ratio

A ratio of a `from_start` segment of `touch` `current` over one of `touch` `previous`, both `origin → peak` over the same series,
with `right_floor` 1e-6, SHALL be missing when the previous wave's value is not greater than 1e-6 or when either side is missing.
A current wave value not greater than 0 SHALL stay a value.

#### Scenario: Previous wave without a rise

- **WHEN** the previous wave's value is 0, negative or at most 1e-6
- **THEN** the ratio SHALL be missing and the entry SHALL not be blocked.

#### Scenario: Weak new wave

- **WHEN** the current wave's rise is 0.5 and the previous wave's rise is 1
- **THEN** the ratio SHALL be 0.5 and a `range` with `min` 0.7 and `bounds exclusive` SHALL block the bar.
