## MODIFIED Requirements

### Requirement: Segment operand shape

A segment reference SHALL be `{"segment": {"episode", "of", "from", "to", "aggregate", "value"?, "span"?, "top"?, "window"?, "negate"?, "eligibility"?}}`;
`episode`, `of`, `from`, `to` and `aggregate` are required and no other field is allowed. Their values are defined by the
requirements "Segment source fields", "Segment aggregation fields", "Segment k-bar change", "Segment absolute-change aggregates" and "Segment eligibility".

#### Scenario: Malformed segment

- **WHEN** a segment names an undeclared episode, an unknown kind, a pair such as `current → peak`, an unknown `aggregate`,
  `value` or `window`, a non-positive `last_n`, a missing required field, or an unknown field such as `select`
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment aggregation fields

`aggregate` SHALL be `sum`, `mean_per_bar`, `max`, `min`, `abs_sum`, `top_abs_sum` or `top_abs_share`. `value` SHALL be `level` (default),
`change` or `change_over`. `window` SHALL be `null` (default, the whole leg) or `{"last_n": N}` with `N` a positive integer.
`negate` SHALL be a boolean, default `false`. `max`, `min`, `abs_sum`, `top_abs_sum` and `top_abs_share` SHALL be allowed only with `value`
`change` or `change_over`, and `sum` and `mean_per_bar` SHALL be rejected with `change_over`. `top_abs_sum` and `top_abs_share` SHALL require `top` (a positive integer) and a non-null `window`; `top`
SHALL be rejected with any other aggregate.

#### Scenario: Invalid aggregation field

- **WHEN** `aggregate`, `value` or `window` has another value, `last_n` is not a positive integer, `max` is used with `level`,
  `sum` is used with `change_over`,
  `top_abs_sum` or `top_abs_share` has no `top` or a null `window`, or `top` is given with another aggregate
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment value

With `x` and the window `s..e` as above, `value = level` SHALL aggregate `x[u]`, `value = change` SHALL aggregate
`Δ[u] = x[u] − x[u−1]` (reading `x[s−1]`) and `value = change_over` SHALL aggregate the `span`-bar changes defined by the requirement "Segment k-bar change", for `u = s..e` (`level`, `change`). `sum` SHALL be the sum and `mean_per_bar` the sum divided by
`bars`; `max`, `min`, `abs_sum`, `top_abs_sum` and `top_abs_share` SHALL be defined by the requirements "Segment extremum aggregates" and "Segment absolute-change aggregates". `negate = true` SHALL multiply the result by −1. Every bar SHALL count with its sign. The value SHALL be missing
when any `x` it reads is non-finite, and its cost SHALL NOT depend on leg lengths.

#### Scenario: Pullback speed toward the anchor

- **WHEN** a segment is the difference EMA5 − EMA500, `peak → current`, `change`, `last_n` 75, `mean_per_bar`, `negate`, long
  side, bar `t`, current touch `m ≥ 1`
- **THEN** its value SHALL be `−(x[t] − x[s−1]) / bars` with `s = max(P_m, t − 74)` and `bars = t − s + 1`.

#### Scenario: Non-finite value inside the window

- **WHEN** a value the window reads is non-finite
- **THEN** the segment SHALL be missing on that bar.

## ADDED Requirements

### Requirement: Segment k-bar change

`value: change_over` SHALL require `span`, a positive integer, and `span` SHALL be rejected with any other `value`. With `x`
the series of `of` (negated on the short side first), the values over the window `s..e` SHALL be
`D[u] = x[u] − x[u−span]` for `u = s+span−1..e`. The earliest value reads `x[s−1]`, and no earlier bar. The result SHALL be
missing when the window has fewer than `span` bars or any `x` read is non-finite.

#### Scenario: Three-bar change on the pullback

- **WHEN** a segment is `peak → current`, `change_over` with `span` 3, `last_n` 75, `min`, `negate`, long side
- **THEN** its value SHALL be `−min` over `u = s+2..t` of `x[u] − x[u−3]` with `s = max(P, t − 74)`.

#### Scenario: Window shorter than the span

- **WHEN** the window has fewer than `span` bars
- **THEN** the segment SHALL be missing.

### Requirement: Segment extremum aggregates

`max` and `min` SHALL return the largest and the smallest value of the series chosen by `value` over the window `s..e`. They
SHALL be missing exactly when the series is missing on the window.

#### Scenario: Strongest move away from the anchor

- **WHEN** a segment is `origin → peak`, `change_over` with `span` 3, `last_n` 75, `max`
- **THEN** its value SHALL be the largest `x[u] − x[u−3]` over the last 75 bars of the impulse.

### Requirement: Segment absolute-change aggregates

`abs_sum` SHALL return the sum of `|v[u]|` and `top_abs_sum` the sum of the `top` largest `|v[u]|` over the window `s..e`,
with `v` the series chosen by `value` (`change` or `change_over`). Every bar of the window SHALL count, whether it moves
toward or away from the anchor. With fewer than `top` values in the window `top_abs_sum` SHALL be the sum of all of them.
Ties SHALL NOT change the sum.

#### Scenario: Five largest changes

- **WHEN** a segment is `peak → current`, `change`, `last_n` 75, `top_abs_sum` with `top` 5
- **THEN** its value SHALL be the sum of the five largest `|x[u] − x[u−1]|` over the last 75 bars of the pullback.

#### Scenario: Window shorter than top

- **WHEN** the window has 3 bars and `top` is 5
- **THEN** `top_abs_sum` SHALL equal `abs_sum`
- **AND** `top_abs_share` SHALL be missing (a window of `top` bars or fewer has no normalized share).

#### Scenario: Normalized share

- **WHEN** a segment is `peak → current`, `change`, `last_n` 75, `top_abs_share` with `top` 5 and the window has `N` > 5 bars
- **THEN** its value SHALL be `(S ÷ A − 5/N) ÷ (1 − 5/N)` with `S` the sum of the five largest `|x[u] − x[u−1]|` and `A` their sum over all `N` bars
- **AND** it SHALL be 0 when all `N` changes have equal magnitude and 1 when only five are non-zero
- **AND** it SHALL be missing when `A` is 0.

### Requirement: Segment eligibility shape

A segment MAY carry `eligibility: {"legs_min_bars", "window", "impulse_positive", "pullback_min_bars"}`. All keys SHALL be optional;
`legs_min_bars`, `window` and `pullback_min_bars` SHALL be positive integers and `impulse_positive` a boolean; `impulse_positive` SHALL require
`window`; unknown keys SHALL be rejected. The `window` of the eligibility SHALL be independent of the segment's own `window`.

#### Scenario: Malformed eligibility

- **WHEN** `eligibility` has an unknown key, a non-positive `legs_min_bars`, `window` or `pullback_min_bars`, a non-boolean `impulse_positive`, or
  `impulse_positive` without `window`
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment eligibility leg length

With `legs_min_bars`, a segment SHALL be missing on bar `t` unless both `origin → peak` and `peak → current` of the current
touch have at least that many bars (inclusive ends), counted on the whole legs before any window. The condition SHALL be
evaluated on the legs of the segment's episode whatever leg the segment itself reads.

#### Scenario: Short leg

- **WHEN** the pullback has 2 bars and `legs_min_bars` is 3
- **THEN** the segment SHALL be missing
- **AND** a range over a ratio of such segments with `empty: pass` SHALL not block the bar.

### Requirement: Segment eligibility pullback length

With `pullback_min_bars` M, a segment SHALL be missing on bar `t` unless `peak → current` of the current touch has at least M
bars (inclusive ends), counted on the whole leg, whatever leg the segment itself reads.

#### Scenario: Boundary

- **WHEN** `pullback_min_bars` is 24 and the pullback has 23 bars, then 24 bars
- **THEN** the segment SHALL be missing on the first and have its value on the second.

### Requirement: Segment eligibility window

With `window` W, a segment SHALL be missing on bar `t` unless every one-bar change of the last W bars of `origin → peak` and
of the last W bars of `peak → current` is finite (each change reads the bar before it). The same two windows SHALL be used
whatever the segment's own `window`, so branches that differ in their own window share one eligibility.

#### Scenario: Non-finite change in the impulse

- **WHEN** one one-bar change in the last W bars of the impulse is non-finite
- **THEN** every segment with that eligibility SHALL be missing on that bar, including one that reads only the pullback.

### Requirement: Segment eligibility impulse direction

With `impulse_positive` true, a segment SHALL be missing on bar `t` unless the sum of the one-bar changes of `x` over the
last `window` bars of `origin → peak` is strictly greater than 0 (the impulse moved away from the anchor). The condition
SHALL be the same for every segment carrying the same eligibility.

#### Scenario: Impulse did not move away

- **WHEN** the impulse sum of changes in its window is 0 or negative
- **THEN** every segment with `impulse_positive` SHALL be missing on that bar.
