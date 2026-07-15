# Indicator and Strategy API compatibility requirements

## Compatibility objective

BBB must be able to replace local calculation behind existing service boundaries without forcing a simultaneous Workbench rewrite.

```text
Workbench frontend
  -> unchanged BBB research_api/BFF
  -> new engine HTTP clients
  -> Strategy/Indicator Engine
```

The API should preserve BBB semantics, not BBB's accidental internal DataFrame classes.

## Shared conventions

- Canonical ticker: `BTCUSDT.P`, `ETHUSDT.P`, etc.
- Time boundaries: integer milliseconds.
- Ranges: aligned half-open `[from_ms, to_ms)`.
- Ordering: strictly ascending by bar open time.
- Values: stable documented numeric representation; indicator values should support exact decimal text where meaningful and `null` during warmup.
- Every response includes engine version and deterministic request/config/plan hash.
- Validation errors are structured and field-addressable for Composer.
- API is coarse-grained; no HTTP call per formula or component.

## Indicator catalog

```http
GET /v1/indicators
GET /v1/indicators/{indicator_id}/schema
POST /v1/indicator-plans/validate
```

Catalog records must expose:

- indicator ID;
- input sources;
- parameter schema/defaults;
- output names;
- supported timeframes;
- batch capability;
- future incremental capability;
- warmup rules.

## Indicator range evaluation

```http
POST /v1/indicator-evaluations/range
```

Request:

```json
{
  "ticker": "BTCUSDT.P",
  "base_timeframe": "5m",
  "from_ms": 1710000000000,
  "to_ms": 1720000000000,
  "features": [
    {
      "feature_id": "ema",
      "output_id": "ema_close_5m_200",
      "timeframe": "5m",
      "parameters": {"period": 200, "source": "close"}
    },
    {
      "feature_id": "adx_dmi",
      "output_id": "adx_dmi_1h_14",
      "timeframe": "1h",
      "parameters": {"period": 14}
    }
  ]
}
```

Response requirements:

- one base-timeframe axis;
- stable `output_id` values compatible with BBB feature/overlay mapping;
- scalar or multi-output series;
- explicit warmup/validity metadata;
- plan hash;
- no Workbench-specific labels or chart DTOs.

## Strategy catalog and validation

```http
GET /v1/strategies
GET /v1/strategies/{strategy_id}/schema
POST /v1/strategies/{strategy_id}/validate
```

The engine must eventually own the authoritative `ema_pullback` schema currently parsed by `instance_loader.py`.

The new consumer may retain its own authoring envelope, but Strategy Engine remains authoritative for strategy semantics. Contract tests must prove:

- accepted configs match;
- rejected configs match;
- normalized spec payloads match;
- config IDs/hashes are deterministic.

## Strategy range evaluation

```http
POST /v1/strategy-evaluations/range
```

Request:

```json
{
  "strategy_id": "ema_pullback",
  "strategy_version": "v1",
  "ticker": "BTCUSDT.P",
  "base_timeframe": "5m",
  "from_ms": 1710000000000,
  "to_ms": 1720000000000,
  "strategy_spec": {},
  "evaluation_profile": "research"
}
```

The service internally performs:

```text
validate spec
 -> build FeaturePlan
 -> read canonical candles from Market Data Service
 -> IndicatorEngine.evaluate_range
 -> context/component evaluation
 -> return decisions/evidence
```

Response must contain enough data to replace BBB calls to:

- `build_feature_plan_from_strategy_spec`;
- `add_feature_columns_from_plan`;
- `build_context_bundle_for_spec`;
- `build_signals_from_spec`;
- `build_exit_outputs_from_spec`;
- the semantic portion of signal trace generation.

Minimum result groups:

- identity/version/config hash;
- base bar axis;
- feature plan metadata;
- requested feature series or retrievable evaluation artifact;
- context series;
- long/short entry decisions;
- profile-aware signal exits;
- stop/take/protection policy outputs;
- component evidence and counters;
- warmup/validity;
- structured strategy state where needed.

The response must not include:

- fills;
- fees/slippage;
- portfolio/trade PnL;
- final BBB `VariantResult`;
- Workbench DTOs.

## Workbench compatibility

BBB continues to own and serve existing Workbench endpoints. BBB adapters translate engine responses into:

- current chart indicator contracts;
- current signal trace contracts;
- component events;
- report and diagnostics structures.

Frontend is not connected directly to the engine during this migration.

## Error model

At minimum:

- `400 invalid_request`;
- `404 strategy_or_indicator_not_found`;
- `409 market_stream_not_ready`;
- `422 validation_failed` with field paths;
- `422 range_not_aligned`;
- `422 range_out_of_bounds`;
- `500 evaluation_invariant_broken`;
- `503 dependency_unavailable`.

## Artifact versus inline response

For normal Workbench windows, inline JSON is acceptable. Large research evaluations may later use an evaluation artifact ID, but pagination/streaming/artifact storage is not required until measured. API DTOs must not assume that all data will always be inline.

## Future bar API reservation

Conceptually reserve:

```http
POST /v1/indicator-evaluations/bar
POST /v1/strategy-evaluations/bar
```

They are not implemented in the extraction phase. Their semantics must reuse the same indicator definitions, strategy components and decision DTOs as range evaluation.


## Normative cross-service seam

The exact two-sided cut between Strategy Engine and Research Service is defined in `docs/12_unified_strategy_research_seam_contract.md`.
