# Design: Strategy Engine foundation v1

## 1. Architectural position

The repository contains two independent application boundaries:

```text
Indicator Engine
  MarketFrame + IndicatorPlan
  → FeatureFrame

Strategy Engine
  StrategySpecEnvelope + market identity/range
  → derives IndicatorPlan
  → invokes Indicator Engine in-process
  → StrategyRangeEvaluationResult
```

They live in one Python package and one FastAPI process for v1. The Strategy application must not call its own HTTP endpoint. HTTP is only an adapter for external consumers such as BBB.

The future live Runtime wrapper remains outside this change. The package layout must reserve clean state models and extension points without implementing incremental behavior.

## 2. Required package layout

```text
src/strategy_engine/
├── domain/
│   ├── market.py
│   ├── ranges.py
│   ├── values.py
│   ├── validity.py
│   └── errors.py
├── indicators/
│   ├── contracts.py
│   ├── application/
│   │   ├── catalog.py
│   │   ├── validate_plan.py
│   │   └── evaluate_range.py
│   └── ports.py
├── strategies/
│   ├── contracts.py
│   ├── application/
│   │   ├── catalog.py
│   │   ├── validate_spec.py
│   │   ├── evaluate_range.py
│   │   └── evaluate_range_batch.py
│   └── ports.py
├── ports/
│   └── market_data.py
├── adapters/
│   ├── http/
│   │   ├── app.py
│   │   ├── dependencies.py
│   │   ├── errors.py
│   │   ├── health.py
│   │   ├── indicator_routes.py
│   │   └── strategy_routes.py
│   └── market_data_service/
│       ├── client.py
│       └── models.py
└── service/
    ├── settings.py
    └── wiring.py
```

Exact filenames may be adjusted when implementation proves a narrower existing owner, but responsibility boundaries may not be merged for convenience.

`legacy_source/` is immutable evidence and must never be placed on the production import path.

## 3. Canonical market contracts

### 3.1 Market identity

```text
MarketStream
- ticker: canonical `.P` ticker such as BTCUSDT.P
- base_timeframe: canonical textual timeframe such as 5m
```

The foundation validates syntax only. Whether a stream is configured and ready is owned by the Market Data Service and enforced by its API response.

### 3.2 Time range

```text
TimeRange
- from_ms: inclusive UTC epoch milliseconds
- to_ms: exclusive UTC epoch milliseconds
```

Requirements:

- `from_ms >= 0`;
- `to_ms > from_ms`;
- boundaries align to the requested base timeframe;
- no implicit clamping or timezone conversion;
- serialization uses integers, not ISO strings.

### 3.3 MarketFrame

The internal core model is transport-neutral and represents ordered canonical OHLCV bars:

```text
MarketFrame
- market: MarketStream
- requested_range: TimeRange
- time_ms: strictly ascending sequence
- open/high/low/close/volume: aligned decimal values
- market_data_hash: deterministic source identity
```

HTTP evaluation requests do not normally carry `MarketFrame`; the application loads it through `MarketDataPort`. Tests may construct it directly.

## 4. Numeric policy

- External OHLCV and indicator numeric values are normalized decimal text.
- `null` represents warmup/unavailable values.
- Timestamps and bar counts are integers.
- Boolean decision masks are JSON booleans.
- No binary float is introduced at the HTTP boundary.
- Internal implementation may later choose Decimal, NumPy, or pandas representations, but conversions must be explicit and parity-tested.

## 5. Indicator contracts

### 5.1 IndicatorPlan

```text
IndicatorPlan
- plan_version
- features: ordered unique PlannedFeature list
- output bindings
- plan_hash
```

```text
PlannedFeature
- feature_id: stable output identity
- kind: indicator kind, e.g. ema
- source: open/high/low/close/volume when applicable
- timeframe
- parameters: JSON-compatible validated mapping
- dependencies: optional feature IDs
```

The foundation validates structural constraints only. Indicator-specific schemas are provided by registered implementations in later changes.

### 5.2 FeatureFrame

```text
FeatureFrame
- market identity and requested range
- time_ms
- series: map output_id → aligned nullable decimal-text sequence
- validity: map output_id → validity metadata
- plan_hash
- market_data_hash
```

Validity metadata supports:

```text
valid_from_ms
warmup_bars
complete
reason
```

### 5.3 Indicator range request

```json
{
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m",
    "from_ms": 1710000000000,
    "to_ms": 1720000000000
  },
  "plan": {
    "plan_version": "1",
    "features": []
  },
  "output": {
    "include_market_axis": true,
    "include_validity": true
  }
}
```

No precomputed OHLCV or feature series are accepted by the public v1 range endpoint.

## 6. Strategy contracts

### 6.1 StrategySpecEnvelope

To support seamless BBB migration, the foundation preserves a generic envelope rather than prematurely inventing a replacement spec:

```text
StrategySpecEnvelope
- strategy_id
- strategy_version
- instance_id / variant_id when supplied
- raw_spec: JSON object preserving the BBB-compatible instance/spec payload
- config_hash when already known
- compatibility_profile, initially bbb_snapshot_20260711
```

Semantic parsing of `ema_pullback` is deferred to its dedicated porting change.

### 6.2 StrategyRangeEvaluationRequest

```json
{
  "strategy": {
    "strategy_id": "ema_pullback",
    "strategy_version": "1",
    "instance_id": "runner_01",
    "raw_spec": {},
    "compatibility_profile": "bbb_snapshot_20260711"
  },
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m",
    "from_ms": 1710000000000,
    "to_ms": 1720000000000
  },
  "output": {
    "include_features": true,
    "include_contexts": true,
    "include_component_evidence": true,
    "include_internal_state": false
  },
  "evaluation_profile": "research"
}
```

The caller supplies strategy identity/spec and market/range identity only. The Strategy application later derives the required indicator plan, loads market data through MDS, invokes Indicator Engine, and evaluates strategy semantics internally.

### 6.3 StrategyRangeEvaluationResult

The result contract reserves the complete groups required by BBB adapters:

```text
identity
market
features
contexts
entries
exit_policy
component_evidence
component_counters
validity
strategy_state_artifact
warnings
```

The foundation must not fabricate these groups. Until `ema_pullback` is ported, evaluation returns an explicit unsupported capability error.

The result explicitly excludes:

- fills;
- orders;
- fees;
- slippage;
- trade records;
- PnL/equity;
- Workbench DTOs.

## 7. Batch contract

`POST /v1/strategy-evaluations/range-batch` is semantically equivalent to multiple range evaluations sharing one market range:

```json
{
  "market": {},
  "variants": [
    {"variant_id": "a", "strategy": {}},
    {"variant_id": "b", "strategy": {}}
  ],
  "output": {},
  "evaluation_profile": "research"
}
```

The foundation defines validation, deterministic ordering, per-variant result/error envelopes, and request limits. It does not implement feature reuse or parallel scheduling yet.

## 8. FastAPI behavior

### 8.1 Health

`GET /health` returns process liveness independent of MDS.

### 8.2 Readiness

`GET /readiness` reports whether the service is configured to perform supported work. During the foundation change it may be ready for catalog/schema requests while evaluation capabilities remain unavailable. Readiness must expose capability status rather than claim full semantic readiness.

Example:

```json
{
  "ready": true,
  "capabilities": {
    "catalog": "ready",
    "indicator_range_evaluation": "not_implemented",
    "strategy_range_evaluation": "not_implemented"
  },
  "dependencies": {
    "market_data_service": "not_required_for_available_capabilities"
  }
}
```

### 8.3 Stable error envelope

```json
{
  "error": "unsupported_capability",
  "message": "ema_pullback range evaluation is not implemented",
  "details": {},
  "request_id": "..."
}
```

Required foundation errors:

- `invalid_request` → 400 or 422 according to FastAPI validation category;
- `unknown_indicator` → 404;
- `unknown_strategy` → 404;
- `unsupported_capability` → 501;
- `market_data_unavailable` → 503;
- `upstream_contract_error` → 502;
- `internal_error` → 500.

No stack traces are returned.

## 9. Market Data Service port

Internal port:

```python
class MarketDataPort(Protocol):
    def get_candles(self, request: MarketRangeRequest) -> MarketFrame: ...
```

The HTTP adapter skeleton targets the existing MDS contract:

```http
GET /v1/candles?ticker=BTCUSDT.P&timeframe=5m&from_ms=...&to_ms=...
```

The client must:

- use configured base URL and timeouts;
- parse decimal text without float conversion;
- preserve half-open range identity;
- reject partial/gapped/upstream-mismatched responses;
- map upstream structured errors;
- avoid any BBB/data-engine import.

The foundation may test the client with a fake HTTP server, but it need not call a real MDS instance.

## 10. Dependency rules

Mandatory structural guards:

- domain modules import no FastAPI, requests/httpx, pandas, NumPy, BBB, or legacy source;
- application modules import contracts and ports, not concrete HTTP clients;
- HTTP routers contain no indicator formulas, strategy logic, or MDS parsing;
- MDS adapter imports no FastAPI router or strategy implementation;
- `legacy_source` is not imported by `src/strategy_engine`;
- Strategy application may invoke Indicator application through an in-process interface, never loopback HTTP;
- central `app.py` and `wiring.py` perform composition only.

## 11. Testing strategy

Foundation acceptance tests include:

- canonical ticker/timeframe/range validation;
- decimal-text parsing/serialization;
- deterministic plan/config hashes;
- request/response schema tests;
- health/readiness/OpenAPI tests;
- unknown/unsupported capability errors;
- batch ordering and per-variant envelope validation;
- MDS client contract tests against a fake server;
- architecture/import guards;
- proof that `legacy_source` is not on the runtime import graph.

No parity claim is made for indicator or strategy semantics in this change.

## 12. First follow-up

The immediate next OpenSpec after foundation is the first Indicator Engine vertical slice:

```text
validated plan
→ MDS candle range
→ EMA calculation
→ FeatureFrame
→ indicator range API
→ golden parity against BBB
```
