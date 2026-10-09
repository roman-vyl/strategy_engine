## ADDED Requirements

### Requirement: Episode history route

The engine SHALL expose `POST /v1/ema-stack-episodes/history`, a read-only route that returns the EMA stack episode history of a market for a parameter set and a side, without a strategy spec.

The request SHALL carry:

- `market`: `ticker`, `base_timeframe`;
- `episode`: `fast_period`, `anchor_period` and `slow_period` (required), and optional `window_bars` and `break_bars`;
- `side`: `long` or `short`;
- optional `page`: `before_start_ms` (a `time_ms` or null, default null) and `limit` (1 to 500, default 50);
- optional `expected_market_data_hash`.

The route SHALL NOT change any stored state other than its in-memory cache.

#### Scenario: History without a strategy

- **WHEN** a request names a market, the three periods and a side
- **THEN** the route SHALL return the newest finished episodes and the current episode of that side
- **AND** no strategy spec SHALL be needed.

### Requirement: Canonical episode parameters

The route SHALL parse `episode` with the same parameter parser as `raw_spec.ema_stack_episode`, with the same defaults (`window_bars` 24, `break_bars` equal to `window_bars`), the same ordering rule `fast_period < anchor_period < slow_period` and the same rejection of unknown keys. A missing period and `history_bars` SHALL be rejected.

#### Scenario: Same rejection as the strategy section

- **WHEN** `episode` has `fast_period` 1000 and `anchor_period` 500
- **THEN** the route SHALL reject the request with the ordering error of the strategy section.

### Requirement: Whole-history computation

The route SHALL compute the episode over the whole committed history of the market, from its earliest to its latest committed candle, with the indicator EMA implementation used by the strategy feature plan and the same per-side projector as strategy evaluation. Censoring SHALL follow `ema-stack-episode-v1` at the start of that history.

#### Scenario: Equal to diagnostics

- **WHEN** a strategy declares `ema_stack_episode` with parameters `p` and is evaluated over the market's whole committed history
- **THEN** every episode, zone, false break and wave of the history route for `p` SHALL equal the diagnostics entity with the same start, by `time_ms` and value.

### Requirement: Pages of whole episodes

A page SHALL hold up to `limit` finished episodes, newest first, that start before `before_start_ms`. A finished episode is one with a stack break. Each SHALL carry its start, its stack break, `censored`, and all its zones, false breaks and waves, with `time_ms` for every point and `known_at`. The response SHALL carry `next_before_start_ms`, the start of the oldest returned episode, or null when no older episode exists.

#### Scenario: Pages cover the history

- **WHEN** a caller follows `next_before_start_ms` from the first page until it is null, over one data version
- **THEN** the union of the pages SHALL be every finished episode of the history exactly once
- **AND** every episode's touch numbers SHALL be the same as in the whole-history computation.

### Requirement: Current episode

Every response SHALL carry `current`: the episode without a stack break as of the latest committed candle, with its zones, false breaks, finished waves, forming wave, `touch_number` and phase at that candle, or null when no episode is active.

#### Scenario: Refresh after a new candle

- **WHEN** a new candle is committed and the first page is requested again
- **THEN** every finished episode returned before SHALL be returned unchanged, identified by its start
- **AND** `current` SHALL reflect the new candle.

### Requirement: One computation per data version

The engine SHALL compute the projection at most once per `(ticker, base_timeframe, effective parameters, side, latest committed candle)` while the entry is in its bounded in-memory cache. Later pages and repeated requests for the same key SHALL be served from the cache. Concurrent requests for the same missing key SHALL compute once. The cache SHALL NOT be persisted.

#### Scenario: Second page does not recompute

- **WHEN** a caller requests the first page and then the second page over the same data version
- **THEN** the projection SHALL be computed once.

### Requirement: Identified response

The response SHALL carry `history_id` (a hash of the market and the effective parameters), the effective parameters, `params_hash` (a hash of the effective parameters and the episode node version), `market_data_hash`, `earliest_ms` and `as_of_ms`. The same request over the same market data SHALL give the same response.

#### Scenario: Repeat request

- **WHEN** the same request is sent twice over unchanged market data
- **THEN** both responses SHALL be equal.
