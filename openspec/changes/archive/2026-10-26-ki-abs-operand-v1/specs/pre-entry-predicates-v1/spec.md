## ADDED Requirements

### Requirement: Absolute value operand shape

An absolute value reference SHALL be `{"abs": <operand>}` with exactly one inner operand. The inner operand SHALL NOT be a
constant, an `abs` or a `ratio`.

#### Scenario: Malformed absolute value

- **WHEN** the inner operand is a constant, an `abs` or a `ratio`
- **THEN** static validation SHALL reject the spec.

### Requirement: Absolute value placement

An absolute value SHALL be accepted wherever its inner operand is accepted, including as a side of a `ratio`. It SHALL be rejected
as the operand of a `change`.

#### Scenario: Absolute value inside change

- **WHEN** a `change` operand is an absolute value
- **THEN** static validation SHALL reject the spec.

### Requirement: Absolute value result

On every bar the value SHALL be the absolute value of the inner operand on that bar. It SHALL be missing where the inner operand
is missing.

#### Scenario: Short impulse

- **WHEN** the close changes by −2.5% over the impulse of a short touch
- **THEN** `abs(leg_change {impulse, close})` SHALL be 2.5 on every bar of that touch.
