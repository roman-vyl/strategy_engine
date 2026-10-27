## ADDED Requirements

### Requirement: At-point identity and cost

An at-point operand SHALL have its own node family whose upstream is its inner operand's node and the episode. A spec without it
SHALL have the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same at-point operand
- **THEN** the at-point operand and its inner operand SHALL each be computed once per batch per side.
