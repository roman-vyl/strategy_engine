## ADDED Requirements

### Requirement: Window change identity and cost

A window change SHALL have its own node family whose upstream is its episode and its feature column. A spec without it SHALL have
the same node set and results as before this change.

#### Scenario: Level candidates share the operand

- **WHEN** a batch contains candidates that differ only in a level over the same window change
- **THEN** the window change SHALL be computed once per batch per side.
