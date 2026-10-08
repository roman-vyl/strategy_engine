## ADDED Requirements

### Requirement: History policy for the EMA stack episode context

For each declared `ema_stack_episode` context, the live history planner SHALL add a requirement of `history_bars` base bars. The warm-up of the provider's three EMA series SHALL be counted by the existing per-feature policy. A spec without an `ema_stack_episode` context SHALL get the same requirements as before this change.

#### Scenario: Episode context with default depth

- **WHEN** a spec declares an `ema_stack_episode` context with default parameters
- **THEN** the resolved requirements SHALL include an entry of 15000 base bars for that context
- **AND** the EMA warm-up entries SHALL be those of the existing EMA policy.

#### Scenario: Episode that starts before the window

- **WHEN** the live window starts inside an episode
- **THEN** that episode SHALL be censored and every predicate reading its fields SHALL be False.
