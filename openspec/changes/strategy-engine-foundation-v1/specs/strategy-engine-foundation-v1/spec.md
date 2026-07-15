# Specification: Strategy Engine foundation v1

## Requirement: Independent service foundation

The repository SHALL provide an installable `strategy_engine` Python package and runnable FastAPI service with clean domain, application, port, adapter, and wiring boundaries.

Production code SHALL NOT import BBB `research`, `research_api`, `data_engine`, frontend contracts, or files under `legacy_source`.

## Requirement: Separate Indicator and Strategy application boundaries

Indicator evaluation and Strategy evaluation SHALL be independent application boundaries inside the same service.

Strategy evaluation MAY call Indicator evaluation through an in-process application interface. It SHALL NOT call the service's own HTTP endpoint.

Indicator code SHALL NOT know strategy sides, blockers, setups, positions, trades, Abi, or Workbench DTOs.

## Requirement: Canonical market identity and range

Every evaluation request SHALL identify a canonical `.P` ticker, canonical base timeframe, inclusive `from_ms`, and exclusive `to_ms`.

The service SHALL reject negative, empty, reversed, or timeframe-unaligned ranges. It SHALL NOT clamp or reinterpret the requested window.

## Requirement: Decimal-text API boundary

OHLCV and indicator numeric values SHALL cross external API boundaries as normalized decimal text. Warmup or unavailable values SHALL be represented as JSON `null`.

The service SHALL NOT silently convert external numeric values through binary float.

## Requirement: Market Data Service abstraction

Application code SHALL depend on a `MarketDataPort`, not on an HTTP client.

The concrete MDS adapter SHALL target `GET /v1/candles`, preserve canonical stream/range identity, parse decimal text, verify ascending complete-grid results, and map upstream structured errors.

A live MDS instance SHALL NOT be required for foundation verification.

## Requirement: Indicator plan and result contracts

The service SHALL define transport-neutral and HTTP schemas for an ordered `IndicatorPlan`, stable feature identities, deterministic plan hash, aligned `FeatureFrame`, and per-series validity metadata.

Indicator-specific formulas and schemas SHALL be provided only by registered implementations. With no implementation registered, evaluation SHALL return an explicit unsupported-capability error and SHALL NOT fabricate a successful result.

## Requirement: BBB-compatible strategy envelope

The service SHALL define a `StrategySpecEnvelope` capable of preserving the current BBB strategy identity, instance/variant identity, raw JSON spec, compatibility profile, and deterministic config identity.

The foundation SHALL NOT semantically parse `ema_pullback`; that responsibility belongs to a later porting change.

## Requirement: Coarse-grained Strategy range API

`POST /v1/strategy-evaluations/range` SHALL accept one strategy envelope plus canonical market/range identity and output options.

The contract SHALL model that the service, not BBB, later derives required features, loads market data, calculates indicators, contexts, entries, and exits internally.

The result schema SHALL reserve groups required for BBB compatibility: identity, market, features, contexts, entries, exit policy, component evidence/counters, validity, optional state artifact, and warnings.

The result SHALL exclude fills, fees, slippage, trades, PnL, equity, and Workbench DTOs.

## Requirement: Coarse-grained batch API

`POST /v1/strategy-evaluations/range-batch` SHALL represent multiple strategy evaluations sharing one market range.

Variant ordering SHALL be deterministic. Each variant SHALL retain its own identity and success/error envelope. The foundation need not implement shared calculation reuse or scheduling.

## Requirement: Catalog and validation APIs

The service SHALL expose indicator and strategy catalog/schema/validation routes.

An empty catalog is valid before semantic ports. Unknown IDs SHALL return structured `404` errors. Unimplemented semantic validation SHALL return structured `501` errors rather than placeholder success.

## Requirement: Capability-aware readiness

`GET /health` SHALL report process liveness.

`GET /readiness` SHALL report readiness per capability and dependency. The service MAY be ready for catalog/schema operations while indicator or strategy evaluation remains `not_implemented`.

Readiness SHALL NOT claim semantic capability that has not been ported.

## Requirement: Stable errors

All application failures SHALL map to a stable JSON envelope containing `error`, `message`, `details`, and `request_id`.

The foundation SHALL distinguish invalid requests, unknown IDs, unsupported capabilities, unavailable market data, upstream contract failures, and internal errors. Stack traces SHALL never be returned.

## Requirement: Architecture enforcement

Automated tests SHALL prove:

- domain code imports no FastAPI, HTTP client, pandas, NumPy, BBB, or legacy modules;
- application code depends on ports rather than concrete adapters;
- HTTP routers contain no SQL, indicator formula, or strategy semantic implementation;
- MDS adapters contain no HTTP route or strategy implementation;
- production code does not import `legacy_source`;
- central app and wiring modules perform composition only.

## Requirement: No semantic overclaim

This change SHALL NOT implement or claim parity for EMA, RSI, ATR, ADX/DMI, HTF enrichment, contexts, entries, exits, managed policy, BBB cutover, or runtime bar-to-bar execution.

The first semantic follow-up SHALL be an EMA Indicator Engine vertical slice with golden parity against BBB.
