# Indicator Engine location and Market Data call path

Indicator Engine lives in the same repository and deployable service as Strategy Engine:

```text
src/strategy_engine/indicators/
src/strategy_engine/strategies/
```

They are separate modules with separate contracts and HTTP APIs, but Strategy Engine calls Indicator Engine directly in Python through `EvaluateIndicatorRange`.

Production candle flow:

```text
Strategy API
-> strategy feature planner
-> Indicator Engine
-> MarketDataPort
-> MarketDataServiceClient
-> Market Data Service GET /v1/candles
```

The caller supplies only strategy identity/spec, ticker, timeframe and range. It does not supply FeaturePlan, candles or calculated indicators.
