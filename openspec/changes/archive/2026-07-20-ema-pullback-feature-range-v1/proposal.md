# Proposal: EMA Pullback Feature Range v1

## Why

The external caller should submit one strategy instance/spec plus market identity and an aligned range. It must not construct an indicator plan or call the Indicator API separately. The Strategy Engine already owns BBB-compatible feature discovery and all currently required indicator implementations, so the next seam is to compose them behind the coarse-grained strategy range endpoint.

## What changes

- Register an `ema_pullback` range evaluator at the feature stage.
- Build the BBB-compatible `IndicatorPlan` from the submitted canonical strategy spec.
- Invoke the Indicator Engine directly in-process.
- Let the Indicator Engine obtain canonical candles through `MarketDataPort`, whose production adapter calls Market Data Service over HTTP.
- Return the complete `FeatureFrame`, feature mappings, hashes and validity metadata from `POST /v1/strategy-evaluations/range`.
- Keep contexts, entries, exits and managed decisions explicitly unavailable.

## Non-goals

- Context construction.
- Entry/exit decisions.
- Managed execution.
- BBB cutover.
- Runtime bar-to-bar evaluation.
