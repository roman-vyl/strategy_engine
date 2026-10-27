## ADDED Requirements

### Requirement: At-point operand shape

An at-point operand SHALL have the shape `{"at_point": {"episode", "point", "operand"}}`. All three fields are required and no
other field is allowed. `point` SHALL be `peak` or `origin`. The inner operand SHALL be an operand of the layer other than a
constant or another at-point operand.

#### Scenario: Malformed at-point

- **WHEN** a field is missing, `point` is another value, the inner operand is a constant or an at-point operand, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: At-point placement

An at-point operand SHALL be accepted wherever a ratio is accepted, including as a side of a ratio or a difference and inside
`abs`. It SHALL be rejected as the operand of a `change`.

#### Scenario: At-point inside change

- **WHEN** a `change` operand is an at-point operand
- **THEN** static validation SHALL reject the spec.

### Requirement: At-point value

On every bar where the current touch of the episode is valid, the value SHALL be the inner operand's value on that touch's point
(`peak` = P, `origin` = S*). It SHALL be missing where the touch is not valid or the inner value at the point is missing or
non-finite. The point SHALL never be later than the bar.

#### Scenario: Ratio read at the peak

- **WHEN** the current touch has its peak on bar 100 and the inner ratio is 0.8 on bar 100 and 0.6 on bar 120
- **THEN** the at-point value with `point: peak` SHALL be 0.8 on bar 120.
