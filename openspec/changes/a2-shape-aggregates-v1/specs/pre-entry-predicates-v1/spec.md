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

`aggregate` SHALL be `sum`, `mean_per_bar`, `max`, `min`, `abs_sum` or `top_abs_sum`. `value` SHALL be `level` (default),
`change` or `change_over`. `window` SHALL be `null` (default, the whole leg) or `{"last_n": N}` with `N` a positive integer.
`negate` SHALL be a boolean, default `false`. `max` and `min` SHALL be allowed only with `value` `change` or `change_over`, and
so SHALL `abs_sum` and `top_abs_sum`. `top_abs_sum` SHALL require `top` (a positive integer) and a non-null `window`; `top`
SHALL be rejected with any other aggregate.

#### Scenario: Invalid aggregation field

- **WHEN** `aggregate`, `value` or `window` has another value, `last_n` is not a positive integer, `max` is used with `level`,
  `top_abs_sum` has no `top` or a null `window`, or `top` is given with another aggregate
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment value

With `x` and the window `s..e` as above, `value = level` SHALL aggregate `x[u]`, `value = change` SHALL aggregate
`Δ[u] = x[u] − x[u−1]` (reading `x[s−1]`) and `value = change_over` SHALL aggregate `x[u] − x[u−span]`, for `u = s..e`. `sum` SHALL be the sum and `mean_per_bar` the sum divided by
`bars`; `max`, `min`, `abs_sum` and `top_abs_sum` SHALL be defined by the requirements "Segment extremum aggregates" and "Segment absolute-change aggregates". `negate = true` SHALL multiply the result by −1. Every bar SHALL count with its sign. The value SHALL be missing
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

`value: change_over` SHALL require `span`, a positive integer, and `span` SHALL be rejected with any other `value`. With `x` the series of
`of` (negated on the short side first) and the window `s..e` of the leg, it SHALL read `D[u] = x[u] − x[u−span]` for
`u = s..e`, hence `x[s−span..e]`. The result SHALL be missing when any `x` it reads is non-finite.

#### Scenario: Three-bar change on the pullback

- **WHEN** a segment is `peak → current`, `change_over` with `span` 3, `last_n` 75, `min`, `negate`, long side
- **THEN** its value SHALL be `−min` over `u = s..t` of `x[u] − x[u−3]` with `s = max(P, t − 74)`.

#### Scenario: Window shorter than the span

- **WHEN** the leg has fewer than `span + 1` bars
- **THEN** the bars before the leg SHALL still be read
- **AND** the value SHALL be missing only if one of them is non-finite.

### Requirement: Segment extremum aggregates

`max` and `min` SHALL return the largest and the smallest value of the series chosen by `value` over the window `s..e`. They
SHALL be missing exactly when the series is missing on the window.

#### Scenario: Strongest move away from the anchor

- **WHEN** a segment is `origin → peak`, `change_over` with `span` 3, `last_n` 75, `max`
- **THEN** its value SHALL be the largest `x[u] − x[u−3]` over the last 75 bars of the impulse.

### Requirement: Segment absolute-change aggregates

`abs_sum` SHALL return the sum of `|v[u]|` and `top_abs_sum` the sum of the `top` largest `|v[u]|` over the window `s..e`,
with `v` the series chosen by `value` (`change` or `change_over`). All bars of the window SHALL count. With fewer than `top`
bars in the window `top_abs_sum` SHALL be missing. Ties SHALL NOT change the sum.

#### Scenario: Five largest changes

- **WHEN** a segment is `peak → current`, `change`, `last_n` 75, `top_abs_sum` with `top` 5
- **THEN** its value SHALL be the sum of the five largest `|x[u] − x[u−1]|` over the last 75 bars of the pullback
- **AND** a window of fewer than 5 bars SHALL give a missing value.

### Requirement: Segment eligibility shape

A segment MAY carry `eligibility: {"legs_min_bars", "impulse_positive"}`. Both keys SHALL be optional, `legs_min_bars` a
positive integer, `impulse_positive` a boolean, and unknown keys SHALL be rejected.

#### Scenario: Malformed eligibility

- **WHEN** `eligibility` has an unknown key, a non-positive `legs_min_bars` or a non-boolean `impulse_positive`
- **THEN** static validation SHALL reject the spec.

### Requirement: Segment eligibility leg length

With `legs_min_bars`, a segment SHALL be missing on bar `t` unless both `origin → peak` and `peak → current` of the current
touch have at least that many bars (inclusive ends). The condition SHALL be evaluated on the legs of the segment's episode
whatever leg the segment itself reads.

#### Scenario: Short leg

- **WHEN** the pullback has 2 bars and `legs_min_bars` is 3
- **THEN** the segment SHALL be missing
- **AND** a range over a ratio of such segments with `empty: pass` SHALL not block the bar.

### Requirement: Segment eligibility impulse direction

With `impulse_positive` true, a segment SHALL be missing on bar `t` unless the mean per-bar change of the series over the
last `N_w` bars of `origin → peak` is greater than 0, with `N_w` the segment's own `last_n` (the whole leg for a null window).

#### Scenario: Impulse did not move away

- **WHEN** `impulse_positive` is true and the impulse mean change in its window is 0 or negative
- **THEN** the segment SHALL be missing.
