## ADDED Requirements

### Requirement: History policy for the EMA stack episode

For each declared episode in `raw_spec.ema_stack_episode`, the live history planner SHALL add a requirement of `history_bars` base bars. The warm-up of the episode's three EMA series SHALL be counted by the existing per-feature policy. A spec without `ema_stack_episode` SHALL get the same requirements as before this change.

#### Scenario: Default depth

- **WHEN** a spec declares an episode in `raw_spec.ema_stack_episode` with default parameters
- **THEN** the resolved requirements SHALL include an entry of 15000 base bars for that episode.

#### Scenario: Episode that started before the window

- **WHEN** the live window starts inside an episode
- **THEN** that episode SHALL be censored and every episode operand reading it SHALL be False.
