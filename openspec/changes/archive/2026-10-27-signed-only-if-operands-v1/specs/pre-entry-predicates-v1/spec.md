## ADDED Requirements

### Requirement: Signed operand

A signed operand SHALL have the shape `{"signed": {"operand", "center"}}`. Both fields are required and no other field is allowed. `center`
SHALL be a finite number and the inner operand SHALL NOT be a constant. On every bar the value SHALL be `center + g · (x − center)`, with
`g` = +1 on the long side and −1 on the short side and `x` the inner value. It SHALL be missing where the inner value is missing.

#### Scenario: Weekly body our way

- **WHEN** the inner value is 0.6 and `center` is 0
- **THEN** the value SHALL be 0.6 on the long side and −0.6 on the short side.

#### Scenario: Close position our way

- **WHEN** the inner value is 0.1 and `center` is 0.5
- **THEN** the value SHALL be 0.1 on the long side and 0.9 on the short side.

### Requirement: Only-if operand shape

An only-if operand SHALL have the shape `{"only_if": {"operand", "require"}}`. Both fields are required and no other field is allowed. The
inner operand SHALL NOT be a constant. `require` SHALL be a non-empty list of `{"operand", "min", "max", "bounds"?}`. Its fields have the
meaning, defaults and validation of a `range`, and `empty` is not accepted.

#### Scenario: Malformed only-if

- **WHEN** `require` is empty, an item carries `empty`, an item operand is a constant, or the operand has an unknown field
- **THEN** static validation SHALL reject the spec.

### Requirement: Only-if value

On every bar the value SHALL be the inner value when every requirement holds. It SHALL be missing otherwise. A requirement holds when its
operand value is finite and inside its bounds.

#### Scenario: Weak yesterday candle

- **WHEN** D1v requires yesterday's body our way ≥ 1 and the body our way is 0.7 on a bar
- **THEN** the value SHALL be missing on that bar whatever today's candle.

#### Scenario: Missing requirement value

- **WHEN** a requirement operand is missing on a bar
- **THEN** the value SHALL be missing on that bar.

### Requirement: Signed and only-if placement

Signed and only-if operands SHALL be accepted wherever a ratio is accepted. They SHALL be rejected as the operand of a `change`.

#### Scenario: Signed inside change

- **WHEN** a `change` operand is a signed operand
- **THEN** static validation SHALL reject the spec.
