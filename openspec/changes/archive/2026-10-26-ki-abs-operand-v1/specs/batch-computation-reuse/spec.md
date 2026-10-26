## ADDED Requirements

### Requirement: Absolute value identity and cost

An absolute value SHALL have its own node family whose upstream is the inner operand's node. A spec without it SHALL have the same
node set and results as before this change.

#### Scenario: Shared inner operand

- **WHEN** a batch contains candidates that differ only in a level over the same ratio with an absolute value
- **THEN** the inner operand, the absolute value and the ratio SHALL each be computed once per batch per side.
