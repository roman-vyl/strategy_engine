## MODIFIED Requirements

### Requirement: Ratio operand

A ratio SHALL have the shape `{"ratio": {"left", "right"}}`, each side an operand of the layer, a ratio included, and not
both constants. Its value SHALL be `left / right`, and SHALL be missing when either side is missing or non-finite or when
`right ≤ 0`.

#### Scenario: Zero denominator

- **WHEN** the right side is 0 on a bar
- **THEN** the ratio SHALL be missing on that bar.

#### Scenario: Ratio of two ratios

- **WHEN** a ratio has a ratio on each side, the right side 0.04 on one bar and 0.2 on another, and `right_floor` 0.05
- **THEN** the outer ratio SHALL be missing on the first bar and `left / 0.2` on the second.
