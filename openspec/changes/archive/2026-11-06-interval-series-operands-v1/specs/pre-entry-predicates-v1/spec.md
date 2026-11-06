## MODIFIED Requirements

### Requirement: Ratio operand

A ratio SHALL have left and right operands, not both constants, and MAY include right_floor and denominator_mode. Mode SHALL be positive (default) or absolute. Positive mode SHALL preserve legacy division semantics. Absolute mode SHALL return left/right when inputs and output are finite and abs(right)>right_floor; otherwise it SHALL be missing. Unknown modes and fields SHALL be rejected.

#### Scenario: Zero denominator
- **WHEN** the right side is 0 with default floor and either mode
- **THEN** the ratio SHALL be missing.

#### Scenario: Ratio of two ratios
- **WHEN** a ratio has a ratio on each side, the right side 0.04 on one bar and 0.2 on another, and right_floor 0.05 in positive mode
- **THEN** the outer ratio SHALL be missing on the first bar and left/0.2 on the second.

#### Scenario: Signed denominator
- **WHEN** left=2, right=-1, right_floor=.02 and denominator_mode=absolute
- **THEN** the result SHALL be -2; with positive mode it SHALL be missing.

### Requirement: Ratio denominator floor

Right_floor SHALL be finite numeric, default 0. Positive mode SHALL preserve the existing check right>right_floor and legacy accepted floor values. Absolute mode SHALL require a nonnegative floor and abs(right)>right_floor. Invalid floors SHALL be rejected. Omitted mode and explicit positive SHALL have the same operand identity as the previous default.

#### Scenario: Tiny positive denominator
- **WHEN** right_floor is 1e-6 and the right side is 1e-7
- **THEN** the ratio SHALL be missing.

#### Scenario: Absolute floor boundary
- **WHEN** absolute mode has right_floor=.02 and right is -.02, 0 or .02
- **THEN** the ratio SHALL be missing in all three cases.

#### Scenario: Invalid absolute floor
- **WHEN** absolute mode has a negative floor
- **THEN** static validation SHALL reject the spec.
