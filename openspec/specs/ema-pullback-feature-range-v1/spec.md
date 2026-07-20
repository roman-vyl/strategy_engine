# EMA Pullback Feature Range v1 Specification

## Purpose

Define the coarse-grained EMA Pullback range-evaluation boundary, internal feature composition, market-data access, response payload, and honest accumulated-stage metadata.

## Requirements

### Requirement: Coarse-grained strategy request

`POST /v1/strategy-evaluations/range` SHALL accept the strategy envelope, canonical ticker, base timeframe, and aligned half-open range. The caller SHALL NOT provide an IndicatorPlan or precomputed features.

#### Scenario: Request an EMA Pullback range evaluation

- **WHEN** a caller submits a strategy envelope and aligned market range
- **THEN** the service SHALL evaluate the range without requiring an `IndicatorPlan` or precomputed features.

### Requirement: Internal feature discovery

For `strategy_id=ema_pullback` and `compatibility_profile=bbb_v1`, the service SHALL build the authoritative BBB-compatible feature plan from `raw_spec`.

#### Scenario: Discover features for a BBB-compatible strategy

- **WHEN** an EMA Pullback BBB v1 range request is accepted
- **THEN** the service SHALL build its authoritative feature plan from `raw_spec`.

### Requirement: In-process Indicator Engine composition

The strategy evaluator SHALL call the Indicator Engine application service directly. It SHALL NOT call the service's own HTTP Indicator API.

#### Scenario: Compose strategy and indicator evaluation

- **WHEN** strategy evaluation requires indicator features
- **THEN** it SHALL invoke the Indicator Engine application service in-process
- **AND** SHALL NOT call the local HTTP Indicator API.

### Requirement: Market Data Service boundary

The Indicator Engine SHALL obtain candles through `MarketDataPort`. The production adapter SHALL call Market Data Service. A successful strategy feature evaluation SHALL require only one market-range load.

#### Scenario: Load candles for one strategy range

- **WHEN** a strategy range evaluation succeeds
- **THEN** candles SHALL be obtained through `MarketDataPort`
- **AND** the requested market range SHALL be loaded exactly once.

### Requirement: Feature payload and honest accumulated stage

The response SHALL include the aligned feature time axis, Decimal-text series, per-series validity, plan hash, market-data hash, and BBB-compatible feature mappings. Response validity SHALL identify the strategy stage currently implemented by the production evaluator; context or decision fields SHALL be populated only when their corresponding readiness flags are true.

#### Scenario: Return a strategy range result

- **WHEN** strategy range evaluation succeeds
- **THEN** the response SHALL include the complete feature payload and hashes
- **AND** its stage and readiness flags SHALL accurately describe every populated semantic layer.

### Requirement: Catalog accuracy

The EMA Pullback catalog entry SHALL advertise range evaluation and SHALL report the exact accumulated evaluation stage and capability flags currently wired into the production evaluator.

#### Scenario: Inspect EMA Pullback range capabilities

- **WHEN** a caller reads the EMA Pullback catalog entry
- **THEN** range evaluation SHALL be advertised as supported
- **AND** the stage and capability flags SHALL match the production evaluator.
