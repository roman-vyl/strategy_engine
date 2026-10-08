## ADDED Requirements

### Requirement: Episode query route

The engine SHALL expose `POST /v1/ema-stack-episodes/range`, a read-only route that returns the EMA stack episode for a market, a display range `[from_ms, to_ms)` and episode parameters, without a strategy spec.

The request SHALL carry:

- `market`: `ticker`, `base_timeframe`, `from_ms`, `to_ms`;
- `episode`: `fast_period`, `anchor_period` and `slow_period` (required), and optional `window_bars`, `break_bars`, `history_bars`;
- optional `sides`, a non-empty subset of `long` and `short`, defaulting to both;
- optional `series`, a list of state or event field names, defaulting to empty;
- optional `expected_market_data_hash`.

The route SHALL NOT change any stored state.

#### Scenario: Query without a strategy

- **WHEN** a request names a market, a display range and the three periods
- **THEN** the route SHALL return the episode of both sides for that range
- **AND** no strategy spec SHALL be needed.

### Requirement: Canonical episode parameters

The route SHALL parse `episode` with the same parameter parser as `raw_spec.ema_stack_episode`, with the same defaults (`window_bars` 24, `break_bars` equal to `window_bars`, `history_bars` 15000), the same ordering rule `fast_period < anchor_period < slow_period` and the same rejection of unknown keys. A missing period SHALL be rejected, since there is no `anchor_stack` to default from.

#### Scenario: Same rejection as the strategy section

- **WHEN** `episode` has `fast_period` 1000 and `anchor_period` 500
- **THEN** the route SHALL reject the request with the ordering error of the strategy section.

### Requirement: History before the display range

The route SHALL compute the episode over `[computed_from_ms, to_ms)`, where `computed_from_ms` is `from_ms` minus `ema_warmup_bars(slow_period) + history_bars` base bars, clamped to the earliest committed candle. Censoring SHALL follow `ema-stack-episode-v1` on the computed range.

#### Scenario: Episode that started before the display range

- **WHEN** an episode starts after `computed_from_ms` plus the slow-EMA warm-up and before `from_ms`
- **THEN** it SHALL NOT be censored
- **AND** its start and its touch numbers SHALL be the same as in a query whose display range starts at its start bar.

### Requirement: One computation path

The route SHALL compute the three EMAs with the indicator EMA implementation used by the strategy feature plan, and the episode with the same per-side projector as strategy evaluation. For the same parameters and the same computed range, its entity tables SHALL equal the episode tables of `/strategy-evaluations/range/diagnostics` for a strategy that declares those parameters, restricted to the display range.

#### Scenario: Equal to diagnostics

- **WHEN** a strategy declares `ema_stack_episode` with parameters `p` and is evaluated over `[computed_from_ms, to_ms)`
- **AND** the query is sent with `p` and `[from_ms, to_ms)`
- **THEN** every zone, false break, wave and episode of the query SHALL equal the diagnostics entity with the same `episode_id` and `number`, by `time_ms` and value.

### Requirement: Compact response

For each requested side the response SHALL carry:

- the episodes, zones, false breaks and waves whose span intersects the display range, with `time_ms` for every point and `known_at`, and without bar indices;
- `segments`: maximal runs of bars with the same `episode_id`, `phase` and `touch_number`, covering the display range without gaps, where `phase` is `none`, `away`, `in_zone`, `in_false_break` or `stack_break`;
- `series` on the display range's `time_ms` axis, only for the requested names.

An entity's span SHALL run from its first point to its last point or its `known_at`, whichever is later; an entity that is not final SHALL run to the last bar.

#### Scenario: Entity crossing the left edge

- **WHEN** a zone starts before `from_ms` and ends inside the display range
- **THEN** the zone SHALL be returned with its real start `time_ms`.

#### Scenario: No dense series by default

- **WHEN** a request has no `series`
- **THEN** the response SHALL carry no per-bar arrays.

### Requirement: Deterministic and identified response

The response SHALL carry the effective parameters, `params_hash` (a hash of the effective parameters and the episode node version), `market_data_hash` and `computed_from_ms`. The same request over the same market data SHALL give the same response.

#### Scenario: Repeat request

- **WHEN** the same request is sent twice over unchanged market data
- **THEN** both responses SHALL be equal, including `params_hash` and `market_data_hash`.
