## ADDED Requirements

### Requirement: Difference operand shape

A difference SHALL have the shape `{"difference": {"left", "right"}}`. Both sides are required, each an operand of the layer (a
ratio or a difference included), and no other field is allowed. Two constant sides SHALL be rejected.

#### Scenario: Malformed difference

- **WHEN** a side is missing, both sides are constants, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Difference placement

A difference SHALL be accepted wherever a ratio is accepted, including as a side of a ratio and inside `abs`. It SHALL be
rejected as the operand of a `change`.

#### Scenario: Difference inside change

- **WHEN** a `change` operand is a difference
- **THEN** static validation SHALL reject the spec.

### Requirement: Difference value

On every bar the value SHALL be `left − right`. It SHALL be missing where either side is missing or non-finite.

#### Scenario: Pullback against impulse

- **WHEN** the left side is −1.5 and the right side 0.8 on a bar
- **THEN** the difference SHALL be −2.3 on that bar.
