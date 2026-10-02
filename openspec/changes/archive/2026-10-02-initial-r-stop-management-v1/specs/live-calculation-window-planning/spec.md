## ADDED Requirements

### Requirement: Initial-R managed stops require no additional history

`initial_r_lock_stop` and `initial_r_trailing_stop` SHALL each have zero
additional semantic lookback. Their inputs SHALL come from the opened trade's
frozen initial risk and managed MFE state, and they SHALL add no indicator
feature to the plan.

#### Scenario: Plan initial-R stops

- **WHEN** a live specification contains either initial-R stop component
- **THEN** live window planning SHALL report zero additional lookback for that rule
- **AND** feature planning SHALL add no ATR or other indicator solely for that stop.
