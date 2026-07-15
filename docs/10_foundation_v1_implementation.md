# Strategy Engine foundation v1 implementation

## Implemented boundary

The repository now contains a runnable but semantically empty FastAPI service with separate Indicator Engine and Strategy Engine application boundaries.

External callers provide:

- strategy or indicator plan identity;
- canonical `.P` ticker;
- base timeframe;
- aligned half-open range `[from_ms, to_ms)`;
- strategy raw spec/instance identity or indicator plan;
- output options.

The service owns future feature discovery, Market Data Service loading, indicator calculation, contexts, and strategy decisions. Those semantics are deliberately not implemented in this foundation.

## Service endpoints

```text
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

Empty catalogs are valid. Unported indicator and strategy semantics return structured `501 unsupported_capability`, never fabricated successful results.

## Internal boundaries

```text
HTTP adapter
→ application service
→ domain contracts / ports
← concrete MDS adapter and registries connected by service wiring
```

Strategy and Indicator applications do not import concrete adapters. Production code never imports `legacy_source` or BBB packages.

## MDS adapter

The foundation includes a real client for the already implemented Market Data Service endpoint:

```text
GET /v1/candles?ticker=...&timeframe=...&from_ms=...&to_ms=...
```

It verifies response identity, decimal-text OHLCV, strictly ascending complete grid, and full requested-window coverage. It is not invoked until an actual indicator evaluator is registered.

## Capability readiness

Process readiness and semantic capability readiness are distinct. The service can be ready for catalog, schema, validation-envelope, and OpenAPI operations while indicator/strategy calculation remains `not_implemented`.

## Next change

The next semantic change is an EMA vertical slice:

```text
BBB EMA contract audit recheck
→ EMA indicator schema and catalog entry
→ EMA evaluator copied semantically from BBB
→ MDS-backed range calculation
→ Indicator API result
→ golden parity against BBB
```
