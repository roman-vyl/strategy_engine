# Proposal: Strategy Engine foundation v1

## Why

BBB currently owns strategy configuration, feature planning, indicator calculation, contexts, entry and exit decisions, execution simulation, reports, diagnostics, and Workbench projections in one repository. The source audit confirms a stable separation boundary after strategy evaluation and before execution simulation, but the new repository does not yet contain the clean contracts needed to port that responsibility safely.

The first implementation change must therefore create a runnable but semantically empty Strategy Engine foundation. It must establish the package boundaries, canonical request/result models, ports, FastAPI contracts, health/readiness behavior, and dependency rules required by all later semantic ports.

This change deliberately does **not** implement EMA, RSI, ATR, ADX/DMI, contexts, entries, exits, managed policy, BBB cutover, or runtime bar-to-bar execution. Those capabilities will be added in subsequent OpenSpec changes against the contracts created here.

## Goals

- Create the independent Python package and FastAPI service foundation.
- Establish Indicator Engine and Strategy Engine as separate application boundaries in one repository and process.
- Define canonical market identity, aligned half-open ranges, decimal-text numeric values, time axes, plans, feature frames, strategy envelopes, decisions, validity metadata, and stable error envelopes.
- Define a Market Data Service port and HTTP client skeleton without yet depending on a concrete indicator implementation.
- Publish catalog, validation, indicator-range, and strategy-range API shapes without claiming semantic support that has not been ported.
- Preserve BBB-compatible strategy instance envelopes and market/range identity so later adapters can replace local calls surgically.
- Add architecture tests that prevent the foundation from collapsing into mixed-responsibility modules.

## Non-goals

- Porting any BBB indicator formula.
- Porting `ema_pullback` config validation or component catalog semantics.
- Returning fabricated indicator or strategy results.
- Supporting batch variants beyond contract models and explicit unsupported responses.
- Implementing managed replay.
- Implementing BBB HTTP clients or changing BBB.
- Implementing Docker runtime composition with MDS or Abi.
- Implementing incremental `evaluate_bar` or runtime strategy instances.

## Proposed external API surface

```http
GET  /health
GET  /readiness
GET  /openapi.json

GET  /v1/indicators
GET  /v1/indicators/{indicator_id}/schema
POST /v1/indicator-plans/validate
POST /v1/indicator-evaluations/range

GET  /v1/strategies
GET  /v1/strategies/{strategy_id}/schema
POST /v1/strategies/{strategy_id}/validate
POST /v1/strategy-evaluations/range
POST /v1/strategy-evaluations/range-batch
```

Catalog endpoints may return an empty catalog in this foundation. Validation and evaluation endpoints for unported implementations must return explicit structured `not_implemented` or `unsupported_capability` responses; they must never return placeholder success data.

## Compatibility position

The foundation accepts the same logical inputs already identified in BBB:

- strategy identity and current BBB-compatible strategy instance/spec envelope;
- canonical ticker and base timeframe;
- aligned half-open range `[from_ms, to_ms)`;
- optional projection/evaluation options;
- variant identity for future batch runs.

The service owns later feature discovery and indicator calculation. BBB will not send precomputed EMA/RSI/ATR/ADX series after cutover. The foundation models this ownership now, while deferring the semantic implementation.

## Expected outcomes

- A runnable service package with clean routers, application services, ports, adapters, and wiring.
- Normative OpenAPI request/response schemas.
- A stable base for the first EMA vertical slice.
- No imports from `research`, `research_api`, `data_engine`, or Workbench/frontend contracts.
