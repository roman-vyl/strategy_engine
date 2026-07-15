# Specification: EMA Pullback Feature Range v1

## Requirement: Coarse-grained strategy request

`POST /v1/strategy-evaluations/range` SHALL accept the strategy envelope, canonical ticker, base timeframe and aligned half-open range. The caller SHALL NOT provide an IndicatorPlan or precomputed features.

## Requirement: Internal feature discovery

For `strategy_id=ema_pullback` and `compatibility_profile=bbb_v1`, the service SHALL build the authoritative BBB-compatible feature plan from `raw_spec`.

## Requirement: In-process Indicator Engine composition

The strategy evaluator SHALL call the Indicator Engine application service directly. It SHALL NOT call the service's own HTTP Indicator API.

## Requirement: Market Data Service boundary

The Indicator Engine SHALL obtain candles through `MarketDataPort`. The production adapter SHALL call Market Data Service. A successful strategy feature evaluation SHALL require only one market-range load.

## Requirement: Feature-stage response

The response SHALL include the aligned feature time axis, Decimal-text series, per-series validity, plan hash, market-data hash and BBB-compatible feature mappings.

The response SHALL identify its stage as `features_ready`. It SHALL indicate that contexts and trading decisions are not ready and SHALL NOT represent empty entry/exit objects as completed strategy decisions.

## Requirement: Catalog accuracy

The EMA Pullback catalog entry SHALL advertise range evaluation at the `features_ready` stage while separately declaring that contexts, decisions and incremental evaluation are unsupported.
