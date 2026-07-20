# Strategy Engine foundation v1 Specification

## Purpose

Define the architectural, contract, and service boundaries for the independent Strategy Engine foundation before indicator and strategy semantics are ported.

## Requirements

### Requirement: Independent service foundation

The repository SHALL provide an installable `strategy_engine` Python package and runnable FastAPI service with clean domain, application, port, adapter, and wiring boundaries.

Production code SHALL NOT import BBB `research`, `research_api`, `data_engine`, frontend contracts, or files under `legacy_source`.

#### Scenario: Start the independent service

- **WHEN** the installed `strategy_engine` package starts its FastAPI application
- **THEN** the service SHALL start through the declared wiring boundary
- **AND** its production import graph SHALL NOT include BBB or `legacy_source` modules.

### Requirement: Separate Indicator and Strategy application boundaries

Indicator evaluation and Strategy evaluation SHALL be independent application boundaries inside the same service.

Strategy evaluation MAY call Indicator evaluation through an in-process application interface. It SHALL NOT call the service's own HTTP endpoint.

Indicator code SHALL NOT know strategy sides, blockers, setups, positions, trades, Abi, or Workbench DTOs.

#### Scenario: Strategy evaluation needs indicator features

- **WHEN** a strategy application service requests indicator evaluation
- **THEN** it SHALL invoke the Indicator application boundary in-process
- **AND** SHALL NOT call the service's own HTTP API.

### Requirement: Canonical market identity and range

Every evaluation request SHALL identify a canonical `.P` ticker, canonical base timeframe, inclusive `from_ms`, and exclusive `to_ms`.

The service SHALL reject negative, empty, reversed, or timeframe-unaligned ranges. It SHALL NOT clamp or reinterpret the requested window.

#### Scenario: Reject an unaligned range

- **WHEN** an evaluation request contains a range boundary that is not aligned to the base timeframe
- **THEN** the service SHALL reject the request
- **AND** SHALL NOT clamp or reinterpret the supplied range.

### Requirement: Decimal-text API boundary

OHLCV and indicator numeric values SHALL cross external API boundaries as normalized decimal text. Warmup or unavailable values SHALL be represented as JSON `null`.

The service SHALL NOT silently convert external numeric values through binary float.

#### Scenario: Serialize an unavailable value

- **WHEN** an indicator value is unavailable because of warmup or missing input
- **THEN** the HTTP response SHALL serialize it as JSON `null`
- **AND** available numeric values SHALL use normalized decimal text.

### Requirement: Market Data Service abstraction

Application code SHALL depend on a `MarketDataPort`, not on an HTTP client.

The concrete MDS adapter SHALL target `GET /v1/candles`, preserve canonical stream/range identity, parse decimal text, verify ascending complete-grid results, and map upstream structured errors.

A live MDS instance SHALL NOT be required for foundation verification.

#### Scenario: MDS returns a gapped range

- **WHEN** the MDS adapter receives candles with a gap or mismatched stream/range identity
- **THEN** it SHALL reject the response as an upstream contract failure
- **AND** application code SHALL remain coupled only to `MarketDataPort`.

### Requirement: Indicator plan and result contracts

The service SHALL define transport-neutral and HTTP schemas for an ordered `IndicatorPlan`, stable feature identities, deterministic plan hash, aligned `FeatureFrame`, and per-series validity metadata.

Indicator-specific formulas and schemas SHALL be provided only by registered implementations. With no implementation registered, evaluation SHALL return an explicit unsupported-capability error and SHALL NOT fabricate a successful result.

#### Scenario: No indicator evaluator is registered

- **WHEN** range evaluation is requested without a registered indicator implementation
- **THEN** the service SHALL return an explicit unsupported-capability error
- **AND** SHALL NOT fabricate a `FeatureFrame`.

### Requirement: BBB-compatible strategy envelope

The service SHALL define a `StrategySpecEnvelope` capable of preserving the current BBB strategy identity, instance/variant identity, raw JSON spec, compatibility profile, and deterministic config identity.

The foundation SHALL NOT semantically parse `ema_pullback`; that responsibility belongs to a later porting change.

#### Scenario: Preserve strategy configuration identity

- **WHEN** a BBB-compatible strategy envelope is accepted
- **THEN** the service SHALL preserve its strategy, instance, raw-spec, and compatibility-profile identity
- **AND** SHALL derive a deterministic config identity.

### Requirement: Coarse-grained Strategy range API

`POST /v1/strategy-evaluations/range` SHALL accept one strategy envelope plus canonical market/range identity and output options.

The contract SHALL model that the service, not BBB, later derives required features, loads market data, calculates indicators, contexts, entries, and exits internally.

The result schema SHALL reserve groups required for BBB compatibility: identity, market, features, contexts, entries, exit policy, component evidence/counters, validity, optional state artifact, and warnings.

The result SHALL exclude fills, fees, slippage, trades, PnL, equity, and Workbench DTOs.

#### Scenario: Submit a strategy range request

- **WHEN** a caller submits one strategy envelope and canonical market range
- **THEN** the endpoint SHALL use the coarse-grained strategy result envelope
- **AND** the result SHALL NOT contain execution fills, fees, PnL, or Workbench DTOs.

### Requirement: Coarse-grained batch API

`POST /v1/strategy-evaluations/range-batch` SHALL represent multiple strategy evaluations sharing one market range.

Variant ordering SHALL be deterministic. Each variant SHALL retain its own identity and success/error envelope. The foundation need not implement shared calculation reuse or scheduling.

#### Scenario: Batch contains multiple variants

- **WHEN** a range-batch request contains multiple ordered variants
- **THEN** the response SHALL preserve their order and identities
- **AND** each variant SHALL have its own result or error envelope.

### Requirement: Catalog and validation APIs

The service SHALL expose indicator and strategy catalog/schema/validation routes.

An empty catalog is valid before semantic ports. Unknown IDs SHALL return structured `404` errors. Unimplemented semantic validation SHALL return structured `501` errors rather than placeholder success.

#### Scenario: Request an unknown catalog item

- **WHEN** a caller requests an unknown indicator or strategy identifier
- **THEN** the service SHALL return a structured `404` error
- **AND** unimplemented semantic validation SHALL return `501` rather than placeholder success.

### Requirement: Capability-aware readiness

`GET /health` SHALL report process liveness.

`GET /readiness` SHALL report readiness per capability and dependency. The service MAY be ready for catalog/schema operations while indicator or strategy evaluation remains `not_implemented`.

Readiness SHALL NOT claim semantic capability that has not been ported.

#### Scenario: Only catalog operations are available

- **WHEN** catalog and schema operations are available but semantic evaluation is not implemented
- **THEN** readiness SHALL report those capabilities separately
- **AND** SHALL NOT claim semantic evaluation readiness.

### Requirement: Stable errors

All application failures SHALL map to a stable JSON envelope containing `error`, `message`, `details`, and `request_id`.

The foundation SHALL distinguish invalid requests, unknown IDs, unsupported capabilities, unavailable market data, upstream contract failures, and internal errors. Stack traces SHALL never be returned.

#### Scenario: Application failure reaches HTTP

- **WHEN** an application error is mapped to an HTTP response
- **THEN** the response SHALL contain `error`, `message`, `details`, and `request_id`
- **AND** SHALL NOT expose a stack trace.

### Requirement: Architecture enforcement

Automated tests SHALL prove:

- domain code imports no FastAPI, HTTP client, pandas, NumPy, BBB, or legacy modules;
- application code depends on ports rather than concrete adapters;
- HTTP routers contain no SQL, indicator formula, or strategy semantic implementation;
- MDS adapters contain no HTTP route or strategy implementation;
- production code does not import `legacy_source`;
- central app and wiring modules perform composition only.

#### Scenario: Run architecture guards

- **WHEN** the repository architecture tests execute
- **THEN** they SHALL enforce the declared domain, application, adapter, wiring, and legacy-import boundaries.

### Requirement: No semantic overclaim

This change SHALL NOT implement or claim parity for EMA, RSI, ATR, ADX/DMI, HTF enrichment, contexts, entries, exits, managed policy, BBB cutover, or runtime bar-to-bar execution.

The first semantic follow-up SHALL be an EMA Indicator Engine vertical slice with golden parity against BBB.

#### Scenario: Inspect foundation capabilities

- **WHEN** only the foundation change is considered
- **THEN** it SHALL NOT claim parity for any deferred indicator or strategy semantics.
