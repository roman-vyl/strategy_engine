# Design: EMA Pullback Feature Range v1

## Runtime call path

```text
BBB / caller
  -> POST /v1/strategy-evaluations/range
  -> EvaluateStrategyRange
  -> EmaPullbackFeatureRangeEvaluator
  -> BuildStrategyFeaturePlan
  -> EvaluateIndicatorRange
  -> MarketDataPort
  -> MarketDataServiceClient
  -> GET Market Data Service /v1/candles
  -> RangeIndicatorEvaluator
  <- FeatureFrame
  <- StrategyRangeResult(stage=features_ready)
```

The Strategy Engine does not call its own Indicator HTTP API. Indicator and Strategy modules live in the same repository and process and communicate through application contracts. The standalone Indicator HTTP API remains available for BBB/Workbench consumers that require indicators without running a strategy.

## Ownership

- Strategy planner owns discovery of required features and BBB-compatible mappings.
- Indicator Engine owns validation and calculation of EMA, ATR, ATR distance, RSI and ADX/DI.
- `MarketDataPort` owns the candle-read boundary.
- `MarketDataServiceClient` is the production HTTP adapter.
- FastAPI routes own transport parsing/serialization only.

## Partial-stage honesty

The response SHALL declare `validity.stage = features_ready`, `contexts_ready = false` and `decisions_ready = false`. Empty entry/exit dictionaries are not equivalent to a trading conclusion; warnings SHALL state that strategy decisions are not yet ported.

## Output

The `features` object contains aligned `time_ms`, Decimal-text series, per-series validity, plan hash, market-data hash and the complete feature-plan mappings needed by subsequent context/component ports and BBB compatibility adapters.
