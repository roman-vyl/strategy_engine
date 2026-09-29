# EMA Pullback Feature Range v1 Specification

## Purpose

Define the coarse-grained EMA Pullback range-evaluation boundary, internal feature composition, market-data access, response payload, and honest accumulated-stage metadata.

## Requirements

### Requirement: Coarse-grained strategy request

`POST /v1/strategy-evaluations/range` SHALL accept the canonical
strategy input (`strategy-evaluation-canonical-input-v1`), canonical
ticker, base timeframe, and aligned half-open range. The caller SHALL
NOT provide an IndicatorPlan or precomputed features, and SHALL NOT
provide `strategy_version`, `instance_id`, or `compatibility_profile`.

#### Scenario: Request an EMA Pullback range evaluation

- **WHEN** a caller submits a canonical strategy input and aligned
  market range
- **THEN** the service SHALL evaluate the range without requiring an
  `IndicatorPlan` or precomputed features.

#### Scenario: Legacy envelope field is supplied

- **WHEN** a range request's `strategy` object contains
  `strategy_version`, `instance_id`, or `compatibility_profile`
- **THEN** strict HTTP validation SHALL reject the request before
  evaluation begins.

### Requirement: Internal feature discovery

For `strategy_id=ema_pullback`, the service SHALL build the
authoritative feature plan from `raw_spec` unconditionally — no
`compatibility_profile` or equivalent selector gates this behavior.

#### Scenario: Discover features for an EMA Pullback strategy

- **WHEN** an EMA Pullback range request is accepted
- **THEN** the service SHALL build its authoritative feature plan from
  `raw_spec` alone.

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
