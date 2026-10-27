## ADDED Requirements

### Requirement: Window change operand shape

A window change SHALL have the shape `{"window_change": {"episode", "of", "last_n", "form"}}`. All four fields are required and
no other field is allowed. `of` SHALL be a feature on the base timeframe, `last_n` a positive integer and `form` either `change`
or `slope`.

#### Scenario: Malformed window change

- **WHEN** a field is missing, `last_n` is not a positive integer, `form` is another value, `of` is on a higher timeframe, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Window change placement

A window change SHALL be accepted wherever a ratio is accepted, including as a side of a ratio or a difference and inside `abs`
or `at_point`. It SHALL be rejected as the operand of a `change`.

#### Scenario: Window change inside change

- **WHEN** a `change` operand is a window change
- **THEN** static validation SHALL reject the spec.

### Requirement: Window change value

On bar t where the current touch of the episode is valid, with P its peak, the window SHALL be `s0 = max(P, t − last_n)` and
`s1 = t`, and `g` SHALL be +1 on the long side and −1 on the short side. With `form: change` the value SHALL be
`g · (x[s1] − x[s0])`; with `form: slope` it SHALL be `g · (x[s1] − x[s0]) / x[s0] / (s1 − s0) · 10⁴`.

#### Scenario: Window clipped at the peak

- **WHEN** `last_n` is 24, P is 10 bars before t, the series rises by 2.0 over those 10 bars and `x[P]` is 100 on the long side
- **THEN** the `slope` value SHALL be `2.0 / 100 / 10 · 10⁴ = 20`, and the `change` value SHALL be 2.0.

#### Scenario: Short side

- **WHEN** the same series is read on the short side
- **THEN** the values SHALL be −20 and −2.0.

### Requirement: Window change missing values

The window change SHALL be missing where the touch is not valid, `s1 ≤ s0`, `x[s0]` or `x[s1]` is not finite, or, with `slope`,
`x[s0]` is 0. No bar after t SHALL be read.

#### Scenario: Evaluated bar is the peak

- **WHEN** t equals P
- **THEN** the window change SHALL be missing on that bar.
