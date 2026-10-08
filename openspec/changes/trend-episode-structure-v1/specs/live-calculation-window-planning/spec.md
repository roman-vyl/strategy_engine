## ADDED Requirements

### Requirement: History policy for the trend episode structure

For each declared `trend_episode` structure, the live history planner SHALL add a requirement of `history_bars` base bars. The warm-up of the structure's three EMA series SHALL be counted by the existing per-feature policy. A spec without `market_structure` SHALL get the same requirements as before this change.

#### Scenario: Default depth

- **WHEN** a spec declares a `trend_episode` structure with default parameters
- **THEN** the resolved requirements SHALL include an entry of 15000 base bars for that structure.

#### Scenario: Episode that started before the window

- **WHEN** the live window starts inside an episode
- **THEN** that episode SHALL be censored and every structure-state predicate on it SHALL be False.
