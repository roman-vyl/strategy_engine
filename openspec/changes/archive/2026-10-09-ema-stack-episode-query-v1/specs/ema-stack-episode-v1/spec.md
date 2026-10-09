## ADDED Requirements

### Requirement: Effective episode parameters in the feature plan

When a spec declares `ema_stack_episode`, the strategy feature plan SHALL carry `episode_params_by_ref`: for each `episode_ref`, the effective parameters after defaults (`fast_period`, `anchor_period`, `slow_period`, `window_bars`, `break_bars`, `history_bars`). A spec without the section SHALL carry no such field, and its plan and `plan_hash` SHALL be unchanged.

#### Scenario: Defaults resolved

- **WHEN** a spec declares `ema_stack_episode: {trend: {}}` with an `anchor_stack` of 500, 1000 and 2000
- **THEN** `episode_params_by_ref.trend` SHALL be `{fast_period: 500, anchor_period: 1000, slow_period: 2000, window_bars: 24, break_bars: 24, history_bars: 15000}`.

### Requirement: One episode computation for every consumer

The engine SHALL have one parameter parser and one per-side projector for the EMA stack episode. Strategy evaluation and `ema-stack-episode-query-v1` SHALL both use them.

#### Scenario: No second parser

- **WHEN** the section parser and the query parser receive the same explicit parameters
- **THEN** both SHALL yield the same `EpisodeParams`.
