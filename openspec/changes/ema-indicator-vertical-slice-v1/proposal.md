# Proposal: EMA Indicator Vertical Slice v1

## Why

The foundation exposes honest Indicator Engine contracts but no semantic indicator implementation. EMA is the first vertical slice because it exercises the complete boundary: catalog/schema, plan validation, Market Data Service range loading, base/HTF calculation, warmup/validity, Decimal-text HTTP output, and golden parity against the copied BBB implementation.

## What changes

- register the `ema` indicator and its authoritative schema;
- validate EMA source, period, timeframe, and dependency-free plan shape;
- implement BBB-compatible range EMA semantics;
- support base timeframe and higher-timeframe EMA alignment;
- expose the implementation through the existing indicator range API;
- update readiness to advertise EMA range evaluation;
- add golden parity tests that execute the copied BBB calculation module;
- preserve `501 unsupported_capability` for all other indicators and all strategies.

## Out of scope

- deriving an IndicatorPlan from `ema_pullback` StrategySpec;
- ATR, RSI, ADX/DMI, contexts, strategy decisions, or runtime incremental EMA;
- BBB cutover or frontend changes;
- caching or persisted feature artifacts.
