# Detailed BBB contract and FastAPI replacement audit

## 1. Audit provenance and rules

Audit source:

- archive: `project_snapshot_20260711.zip`;
- SHA-256: `3020cf491a185e495c16b77caddb9e8c06acb7e6577d6b6d9fe5efc9373046e6`;
- package: `research/strategies/ema_pullback`;
- source copy: `legacy_source/bbb/research/strategies/ema_pullback`;
- copy manifest: `legacy_source/bbb/copy_manifest.json`.

This document is normative for the first OpenSpec. Every described contract must be rechecked against the immutable copy immediately before its implementation slice.

Terminology:

- **current call** — actual BBB Python call in the snapshot;
- **engine core call** — target in-process application/domain contract;
- **FastAPI replacement** — process/repository boundary used by BBB after cutover;
- **compatibility adapter** — BBB-side translation that preserves existing BBB downstream interfaces;
- **projection** — requested subset of a range evaluation result.

## 2. Top-level current caller chain

### 2.1 CLI/direct run

```text
research/strategies/ema_pullback/run.py
  → execution/runner.py::run_strategy_specs_from_config
  → research/experiments/config_loader.py::load_strategy_config_file
  → instance_loader.py::load_ema_pullback_config_entry
  → execution/data_loader.py::load_candles_once
  → execution/backtest.py::run_strategy_spec for every variant
  → results/report writers
```

### 2.2 Experiment batch

```text
research/experiments/batch_runner.py
  → execution/runner.py::run_strategy_specs_from_config_returning_paths
  → same config/data/backtest path
```

### 2.3 Research API backtest

```text
research_api/services/backtest_service.py
  → run config validation
  → execution/runner.py::run_strategy_specs_from_config
```

### 2.4 Workbench trace

```text
research_api/services/signal_trace_service.py::fetch_signal_trace_bundle
  → load report/variant
  → strategy_spec_from_report_dict
  → legacy DB OHLCV read with warmup
  → build_feature_plan_from_strategy_spec
  → add_feature_columns_from_plan
  → build_signal_trace_from_spec
  → SignalTraceBundle BFF contract
```

This path independently recomputes indicator and strategy semantics and therefore must be migrated to the same Strategy Engine range-evaluation artifact as backtest evaluation.

## 3. Seam A — strategy instance parsing and validation

### 3.1 Current Python call

Caller:

```text
research/experiments/config_loader.py
```

Callee:

```python
load_ema_pullback_config_entry(
    instance: Mapping[str, Any]
) -> LoadedEmaPullbackInstance
```

Source:

```text
research/strategies/ema_pullback/instance_loader.py:119
```

Nested call:

```python
load_ema_pullback_instance(
    instance: Mapping[str, Any]
) -> EmaPullbackStrategySpec
```

### 3.2 Current input

The input is one existing BBB external-config instance mapping. Top-level fields:

```text
instance_id
variant                    optional/legacy-compatible according to parser
market
strategy
```

`market` supplies at least symbol and timeframe. `strategy` supplies:

```text
trade_sides
anchor_stack
direction
setups
trigger
blockers
risk
trade_management
contexts
```

The current parser:

- rejects unknown fields;
- enforces required fields;
- resolves component IDs through the component registry;
- parses contexts and context consumption;
- parses exit policy profiles;
- parses phase, stop, take and runtime-exit management rules;
- validates globally unique instance IDs;
- creates an immutable `EmaPullbackStrategySpec`;
- computes `strategy_spec_config_id(spec)`.

### 3.3 Current return

```python
@dataclass(frozen=True)
class LoadedEmaPullbackInstance:
    spec: EmaPullbackStrategySpec
    strategy_spec_config_id: str
```

Downstream uses:

- `spec.symbol` and `spec.base_timeframe` for shared-market validation;
- full `spec` for feature planning/evaluation;
- config ID for result identity and reporting;
- normalized `strategy_spec_to_dict(spec)` for report payloads and later signal-trace reconstruction.

### 3.4 Target owner

Strategy Engine config/validation application.

Clean internal contract:

```python
validate_ema_pullback_instance(raw_instance) -> ValidatedStrategyInstance
```

### 3.5 FastAPI replacement

```http
POST /v1/strategies/ema_pullback/validate
Content-Type: application/json
```

Request deliberately preserves the existing BBB instance shape:

```json
{
  "instance": {
    "instance_id": "runner_01",
    "variant": "runner_01",
    "market": {
      "symbol": "BTCUSDT.P",
      "timeframe": "5m"
    },
    "strategy": {
      "trade_sides": ["long", "short"],
      "anchor_stack": {},
      "direction": {},
      "setups": [],
      "trigger": {},
      "blockers": [],
      "risk": {},
      "trade_management": {},
      "contexts": {}
    }
  },
  "compatibility_profile": "bbb_snapshot_20260711"
}
```

Success response:

```json
{
  "strategy_id": "ema_pullback",
  "strategy_version": "1",
  "strategy_spec_config_id": "sha256-or-current-compatible-id",
  "normalized_strategy_spec": {},
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m"
  },
  "warnings": []
}
```

Validation response:

```json
{
  "error": "validation_failed",
  "message": "strategy instance is invalid",
  "issues": [
    {
      "path": "strategy.trade_management.exit_policy.profiles.aligned.exits[0]",
      "code": "unknown_component",
      "message": "..."
    }
  ]
}
```

### 3.6 BBB compatibility adapter

Initially BBB can preserve `LoadedExternalConfig` and `EmaPullbackStrategySpec` consumers by translating `normalized_strategy_spec` into a temporary BBB-side read model. Final cutover should remove BBB semantic validation, but BBB may retain envelope validation for experiment-level fields.

### 3.7 Parity acceptance

- every currently accepted config fixture accepted;
- every currently rejected fixture rejected;
- issue paths are at least as specific as current exceptions;
- normalized payload semantically identical;
- config ID stable or one-time migration explicitly approved;
- no `research.*` imports in the new validator.

## 4. Seam B — feature plan construction

### 4.1 Current Python call

```python
build_feature_plan_from_strategy_spec(
    spec: EmaPullbackStrategySpec
) -> FeaturePlan
```

Source:

```text
research/strategies/ema_pullback/features/plan.py:243
```

Current production callers:

- `execution/backtest.py::run_strategy_spec`;
- `research_api/services/signal_trace_service.py::fetch_signal_trace_bundle`;
- diagnostics and tests.

### 4.2 Current input

Full validated `EmaPullbackStrategySpec`.

The planner inspects:

- anchor-stack EMA specs;
- setup feature requirements;
- blocker RSI/ADX/EMA requirements;
- context provider EMA requirements;
- exit rule EMA/RSI/distance requirements;
- phase-rule ATR/ADX requirements;
- managed stop/take/runtime-exit feature references.

### 4.3 Current return

```python
@dataclass(frozen=True)
class FeaturePlan:
    features: tuple[PlannedFeature, ...]
    anchor_columns: dict[str, str]
    exit_distance_columns: dict[str, str]
    rsi_columns: dict[tuple[str, int], str]
    adx_dmi_columns: dict[tuple[str, int], dict[str, str]]
    setup_columns_by_instance_id: dict[str, dict[str, str]]
    ema_columns: dict[tuple[str, int], str]
    htf_context_columns_by_ref: dict[str, dict[str, str]]
```

`PlannedFeature` fields:

```text
feature_id
kind
source
timeframe
period
base_feature_id
multiplier
```

Downstream consumers use plan maps to find exact DataFrame columns without independently reconstructing names.

### 4.4 Target owner

Indicator Engine planning application. Strategy Engine asks it to derive a plan from validated strategy requirements.

### 4.5 FastAPI replacement

Direct public use:

```http
POST /v1/indicator-plans/derive-from-strategy
```

Request:

```json
{
  "strategy_id": "ema_pullback",
  "strategy_version": "1",
  "normalized_strategy_spec": {},
  "base_timeframe": "5m"
}
```

Response:

```json
{
  "plan_hash": "sha256...",
  "features": [
    {
      "feature_id": "ema_close_base_200",
      "kind": "ema",
      "source": "close",
      "timeframe": "5m",
      "period": 200,
      "base_feature_id": null,
      "multiplier": null
    }
  ],
  "bindings": {
    "anchor_columns": {
      "fast": "ema_close_base_50",
      "anchor": "ema_close_base_200",
      "slow": "ema_close_base_500"
    },
    "exit_distance_columns": {},
    "rsi_columns": {},
    "adx_dmi_columns": {},
    "setup_columns_by_instance_id": {},
    "ema_columns": {},
    "htf_context_columns_by_ref": {}
  }
}
```

BBB backtest should not call this endpoint separately after final migration. It is exposed for catalog/debug/parity. `POST /v1/strategy-evaluations/range` derives and uses the plan internally in one coarse call.

### 4.6 Parity acceptance

- exact feature set;
- exact stable IDs/bindings;
- deterministic ordering;
- no duplicate equivalent feature;
- plan hash deterministic;
- current tests for feature profile/setup/context requirements ported.

## 5. Seam C — indicator range calculation

### 5.1 Current Python call

```python
add_feature_columns_from_plan(
    df: pandas.DataFrame,
    plan: FeaturePlan
) -> pandas.DataFrame
```

Source:

```text
research/strategies/ema_pullback/features/calculations.py:125
```

### 5.2 Current input

A DataFrame with:

- `DatetimeIndex` aligned to base timeframe;
- required columns `open`, `high`, `low`, `close`, `volume`;
- finite market values expected by downstream logic;
- `FeaturePlan` naming every required feature.

Current calculation ownership:

- EMA using pandas EWM semantics;
- true range and ATR rolling mean;
- RSI rolling mean;
- Wilder RMA ADX/DMI;
- HTF OHLCV resampling;
- alignment of only completed HTF values to base bars;
- ATR-distance derived series;
- preservation of original OHLCV and index.

### 5.3 Current return

A copy/enriched DataFrame containing original OHLCV plus every planned feature column. Callers access columns using `FeaturePlan` bindings.

### 5.4 Target owner

Indicator Engine batch evaluator.

Internal target:

```python
IndicatorEngine.evaluate_range(
    market_frame: MarketFrame,
    plan: IndicatorPlan
) -> FeatureFrame
```

### 5.5 FastAPI replacement

```http
POST /v1/indicator-evaluations/range
```

Request:

```json
{
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m",
    "from_ms": 1710000000000,
    "to_ms": 1720000000000
  },
  "plan": {
    "features": [
      {
        "feature_id": "ema_close_base_200",
        "kind": "ema",
        "source": "close",
        "timeframe": "5m",
        "period": 200
      }
    ]
  },
  "output": {
    "include_market_axis": true,
    "include_validity": true
  }
}
```

The HTTP facade loads canonical candles through the Market Data Service port. The core itself receives a `MarketFrame` and has no HTTP dependency.

Response:

```json
{
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m",
    "from_ms": 1710000000000,
    "to_ms": 1720000000000,
    "bar_count": 1000,
    "market_data_hash": "sha256..."
  },
  "plan_hash": "sha256...",
  "time_ms": [1710000000000, 1710000300000],
  "series": {
    "ema_close_base_200": [null, "68450.12"]
  },
  "validity": {
    "ema_close_base_200": {
      "valid_from_ms": 1710060000000,
      "warmup_bars": 199
    }
  }
}
```

Numeric output is Decimal text where practical. `null` represents unavailable/warmup values. Exact calculation precision/tolerance is fixed in the first indicator OpenSpec.

### 5.6 Workbench compatibility

Current chart overlay EMA under `research_api/services/indicators.py` is explicitly a view-layer indicator and not the strategy feature pipeline. During migration BBB BFF may map chart overlay requests to Indicator API, but must preserve existing frontend DTOs and chart-time seconds. The engine returns backend milliseconds and no `IndicatorPoint` frontend model.

### 5.7 Parity acceptance

- exact time axis;
- no incomplete-HTF lookahead;
- EMA/ATR/RSI/ADX/DI parity;
- warmup/NaN parity;
- exact feature IDs;
- source market hash recorded for comparison.

## 6. Seam D — context bundle

### 6.1 Current Python call

```python
build_context_bundle_for_spec(
    spec: EmaPullbackStrategySpec,
    df: pandas.DataFrame,
    plan: FeaturePlan
) -> ContextBundle | None
```

Source:

```text
research/strategies/ema_pullback/context/pipeline.py:12
```

### 6.2 Current behavior

- returns `None` when `spec.contexts` is empty;
- otherwise iterates `(context_ref, provider)`;
- resolves planned HTF fast/anchor/slow columns;
- if columns are missing, emits neutral masks;
- otherwise calls `htf_context`;
- stores `ContextOutput(context_ref, provider, masks)`.

`ContextOutput.state_series()` produces string state by mask.

### 6.3 Target owner

Strategy Engine context evaluation. It consumes `FeatureFrame`, not raw MDS client or HTTP.

### 6.4 FastAPI representation

Context is returned as part of `POST /v1/strategy-evaluations/range`, not as one RPC per context.

Response fragment:

```json
{
  "contexts": {
    "htf_1": {
      "provider": {
        "component_id": "htf_ema_stack_context",
        "timeframe": "1h",
        "source": "close",
        "fast_period": 50,
        "anchor_period": 200,
        "slow_period": 500
      },
      "state": ["neutral", "up", "up"],
      "masks": {
        "up": [false, true, true],
        "down": [false, false, false],
        "neutral": [true, false, false]
      }
    }
  }
}
```

### 6.5 Acceptance

- exact state/mask parity;
- missing-feature fallback parity until explicitly redesigned;
- context reference lookup parity;
- side-relative consumption tested separately.

## 7. Seam E — entry signal evaluation

### 7.1 Current Python call

```python
build_signals_from_spec(
    df: pandas.DataFrame,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    *,
    context_bundle: ContextBundle | None = None
) -> PortfolioSignals
```

Source:

```text
research/strategies/ema_pullback/execution/signals.py:272
```

### 7.2 Internal current call sequence

For each enabled side:

```text
resolve direction component
→ direction_fn(df, fast_col, anchor_col, slow_col, side)
→ evaluate every blocker
→ apply blocker context gate
→ compose blockers
→ compose setup masks
→ run setup trace for counters where required
→ trigger_fn(...)
→ risk_fn(df, side)
→ compose_final_signals
```

### 7.3 Current return

```python
@dataclass(frozen=True)
class PortfolioSignals:
    entries: pandas.Series
    short_entries: pandas.Series
    output_counters: tuple[dict[str, Any], ...]
```

`entries` and `short_entries` are bar-aligned bool series. `output_counters` contains blocker/setup evidence used in reports.

### 7.4 Target owner

Strategy Engine entry evaluation.

Internal target:

```python
EntryEvaluator.evaluate_range(
    spec,
    feature_frame,
    context_outputs
) -> EntryEvaluation
```

### 7.5 FastAPI replacement

No separate HTTP call for entries. It is a result group in:

```http
POST /v1/strategy-evaluations/range
```

Response fragment:

```json
{
  "entries": {
    "long": [false, true, false],
    "short": [false, false, false],
    "stop_ready_applied": false
  },
  "component_evidence": {
    "long": {
      "direction_ok": [true, true, true],
      "blockers_ok": [true, true, false],
      "setup_ok": [false, true, true],
      "trigger_ok": [false, true, false],
      "risk_ok": [true, true, true]
    },
    "short": {}
  },
  "component_counters": []
}
```

Important compatibility distinction:

- `PortfolioSignals.entries` is strategy entry before `stop_ready` gating;
- current backtest creates `entries_for_portfolio = entries & stop_ready_long`;
- response must preserve both raw strategy entry and optionally derived portfolio-ready entry to avoid silent semantic changes.

### 7.6 Acceptance

- raw entry parity by bar and side;
- blocker/setup/trigger/risk mask parity;
- output counter parity;
- disabled-side parity;
- no Workbench labels/tooltips in core result.

## 8. Seam F — static exit/protection evaluation

### 8.1 Current Python call

```python
build_exit_outputs_from_spec(
    df: pandas.DataFrame,
    spec: EmaPullbackStrategySpec,
    plan: FeaturePlan,
    *,
    context_bundle: ContextBundle | None = None
) -> PortfolioExitOutputs
```

Source:

```text
research/strategies/ema_pullback/execution/exits.py:223
```

### 8.2 Current behavior

- resolves every exit component from always-on and profile groups;
- computes signal exit series per side/rule;
- computes distance series and converts to ratio against close;
- evaluates exit-profile context consumption;
- compiles profile-specific exits, SL and TP;
- selects current profile series;
- computes `stop_ready`;
- builds output counters;
- builds `ExitAttributionContext` used later by BBB trade extraction/reporting.

### 8.3 Current return fields

```text
exits
short_exits
sl_stop
tp_stop
stop_ready_long
stop_ready_short
context_state
profile_long
profile_short
long_exits_by_profile
short_exits_by_profile
sl_stop_by_profile
tp_stop_by_profile
output_counters
attribution
```

### 8.4 Target owner

Strategy Engine static exit/protection policy.

### 8.5 FastAPI response fragment

```json
{
  "exit_policy": {
    "selected": {
      "long_signal_exit": [false, false, true],
      "short_signal_exit": [false, false, false],
      "long_sl_ratio": ["0.02", "0.02", "0.02"],
      "short_sl_ratio": ["0.02", "0.02", "0.02"],
      "long_tp_ratio": ["0.06", "0.06", "0.06"],
      "short_tp_ratio": ["0.06", "0.06", "0.06"],
      "stop_ready_long": [true, true, true],
      "stop_ready_short": [true, true, true]
    },
    "profiles": {
      "profile_long": ["neutral", "aligned", "aligned"],
      "profile_short": ["neutral", "countertrend", "countertrend"],
      "long_exits_by_profile": {},
      "short_exits_by_profile": {},
      "sl_ratio_by_profile": {},
      "tp_ratio_by_profile": {}
    },
    "attribution": {
      "rules": [],
      "context_state": []
    }
  }
}
```

### 8.6 BBB adapter

BBB converts Decimal text ratios into the numeric arrays expected by vectorbt or current managed replay. Attribution response must retain rule instance IDs, rule groups, kinds and per-bar signal/distance evidence sufficient to reproduce current `ExitAttributionContext` behavior.

### 8.7 Acceptance

- signal exits parity;
- profile selection parity;
- SL/TP ratio parity;
- stop-ready parity;
- attribution rule identity parity;
- profile-specific arrays parity.

## 9. Seam G — one coarse strategy range evaluation

The final BBB replacement must not perform five HTTP calls for plan, features, contexts, entries and exits. The repository/process seam is one application call.

### 9.1 FastAPI request

```http
POST /v1/strategy-evaluations/range
```

```json
{
  "strategy": {
    "strategy_id": "ema_pullback",
    "strategy_version": "1",
    "strategy_spec_config_id": "...",
    "normalized_strategy_spec": {}
  },
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m",
    "from_ms": 1710000000000,
    "to_ms": 1720000000000
  },
  "output_projection": {
    "feature_plan": true,
    "feature_series": "required_only",
    "contexts": true,
    "entries": true,
    "exit_policy": true,
    "component_evidence": "summary",
    "component_events": false,
    "trace": false
  },
  "compatibility_profile": "bbb_snapshot_20260711"
}
```

### 9.2 FastAPI response

```json
{
  "evaluation_id": "uuid",
  "engine_version": "...",
  "strategy": {
    "strategy_id": "ema_pullback",
    "strategy_version": "1",
    "strategy_spec_config_id": "..."
  },
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m",
    "from_ms": 1710000000000,
    "to_ms": 1720000000000,
    "bar_count": 1000,
    "market_data_hash": "sha256..."
  },
  "time_ms": [],
  "feature_plan": {},
  "features": {},
  "contexts": {},
  "entries": {},
  "exit_policy": {},
  "component_counters": [],
  "component_evidence": {},
  "validity": {
    "evaluation_ready": [],
    "warmup_complete_from_ms": 0
  }
}
```

### 9.3 Current BBB replacement point

In `run_strategy_spec`, replace only this block:

```python
plan = build_feature_plan_from_strategy_spec(spec)
enriched = add_feature_columns_from_plan(ohlcv, plan)
context_bundle = build_context_bundle_for_spec(spec, enriched, plan)
signals = build_signals_from_spec(...)
exit_outputs = build_exit_outputs_from_spec(...)
```

with:

```python
evaluation = strategy_engine_client.evaluate_range(...)
plan = evaluation_adapter.feature_plan(evaluation)
enriched = evaluation_adapter.enriched_frame(ohlcv, evaluation)
context_bundle = evaluation_adapter.context_bundle(evaluation)
signals = evaluation_adapter.portfolio_signals(evaluation)
exit_outputs = evaluation_adapter.portfolio_exit_outputs(evaluation)
```

These adapters document how a new consumer service can translate Strategy Engine responses into research-owned execution inputs. They do not connect to or execute the original BBB runtime.

## 10. Seam H — multi-variant shared-market evaluation

Current runner loads OHLCV once and calls `run_strategy_spec` for every spec. The API must not force a separate MDS load for every variant.

### 10.1 FastAPI request

```http
POST /v1/strategy-evaluations/range-batch
```

```json
{
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m",
    "from_ms": 1710000000000,
    "to_ms": 1720000000000
  },
  "strategies": [
    {
      "request_key": "variant-a",
      "strategy_id": "ema_pullback",
      "strategy_spec_config_id": "...",
      "normalized_strategy_spec": {}
    },
    {
      "request_key": "variant-b",
      "strategy_id": "ema_pullback",
      "strategy_spec_config_id": "...",
      "normalized_strategy_spec": {}
    }
  ],
  "output_projection": {}
}
```

Response:

```json
{
  "market": {
    "bar_count": 1000,
    "market_data_hash": "sha256..."
  },
  "evaluations": [
    {"request_key": "variant-a", "status": "success", "result": {}},
    {"request_key": "variant-b", "status": "success", "result": {}}
  ]
}
```

Failure isolation must be explicit: one invalid variant may fail without hiding successful variants, while market-load failure fails the whole request.

## 11. Seam I — Workbench signal trace

### 11.1 Current call

```python
fetch_signal_trace_bundle(
    *,
    run_id: str,
    variant_key: str,
    from_ms: int,
    to_ms: int | None,
    to_open_time_ms: int | None,
    context_overlay_ref: str | None,
    db_path: Path | None
) -> research_api.contracts.SignalTraceBundle
```

The service reconstructs a spec from report JSON and recomputes the feature/strategy pipeline.

### 11.2 Target call

BBB BFF keeps the same public endpoint and input query. Internally it calls:

```http
POST /v1/strategy-evaluations/range
```

with:

```json
{
  "strategy": {"normalized_strategy_spec": {}},
  "market": {
    "ticker": "BTCUSDT.P",
    "base_timeframe": "5m",
    "from_ms": "including required warmup",
    "to_ms": 1720000000000
  },
  "output_projection": {
    "feature_series": "trace_required",
    "contexts": true,
    "entries": true,
    "exit_policy": true,
    "component_evidence": "full",
    "component_events": true,
    "trace": true,
    "context_overlay_ref": "htf_1"
  }
}
```

### 11.3 Engine output versus BFF output

Engine returns milliseconds, semantic masks, raw metadata and events. BBB translates to existing:

```text
SignalTraceBundle
SideSignalTrace
HtfContextTrace
ContextConsumptionTraceRecord
ComponentEvent
```

BBB remains owner of:

- Unix seconds for chart;
- labels/tooltips;
- slicing/max-bars policy;
- frontend Pydantic contracts;
- cache keyed by run/variant/window;
- endpoint compatibility.

Where current `signal_trace.py` mixes semantic evidence and presentation labels, it must be split. Semantic event type, role, side, component ID, instance ID, span identity and raw metadata move to engine. Human tooltip formatting remains BBB.

### 11.4 Acceptance

- existing `/api/...signal-trace` output unchanged;
- long/short masks parity;
- HTF context parity;
- context consumption parity;
- component event times/identity parity;
- tooltip wording may only change through separately approved frontend contract.

## 12. Seam J — component catalog and Composer

### 12.1 Current call

```python
research_api.services.component_catalog.get_component_catalog(
    *, family: str = "ema_pullback"
) -> ComponentCatalog
```

Current catalog is BBB-owned and duplicates component IDs, parameters, defaults and descriptions.

### 12.2 FastAPI replacement

```http
GET /v1/strategies/ema_pullback/catalog
```

Response must carry all fields currently required by BBB `ComponentCatalog`, including:

- sections;
- components by role;
- parameter schemas;
- context providers;
- context-consumption roles/policies;
- management rule schemas;
- schema version;
- capability flags.

BBB `research_api` keeps its current frontend endpoint and converts engine catalog schema to existing Pydantic contracts until frontend migration is separately approved.

### 12.3 Acceptance

- Composer renders same controls/defaults;
- valid draft payloads remain valid;
- unsupported combinations remain rejected;
- no second authoritative catalog in BBB after cutover.

## 13. Seam K — managed policy and execution

This seam is the same physical cut consumed by the new Research Service. See
`docs/12_unified_strategy_research_seam_contract.md` for the normative two-sided
mapping.

### 13.1 Legacy mixed loop

The legacy loop mixes strategy policy with research execution:

```text
bar open
  -> inherited ActiveManagementSnapshot
  -> ManagedExitProvider.get_bar_open_candidates
  -> OHLC hit detection and arbitration
  -> possible fill/close
  -> TradeRuntimeState update
  -> ManagedExitProvider.update_end_of_bar_snapshot
  -> next ActiveManagementSnapshot
```

### 13.2 Strategy Engine side

Strategy Engine owns and returns:

- phase transitions;
- feature/ATR/ADX lookup semantics;
- managed stop calculations;
- take-profile switching;
- runtime-exit activation;
- effective-from timing;
- ordered strategy management events.

The authoritative endpoint is:

```http
POST /v1/strategy-evaluations/managed-replay
```

It evaluates one already-open logical trade over a range and returns per-bar
policy state/events. End-of-bar decisions become executable from the next bar.
It does not perform fill arbitration and does not create trade records.

### 13.3 Research Service side

Research Service owns:

- current position execution state;
- candidate-hit detection against open/high/low/close;
- gap execution and same-bar priority;
- fill prices, fees, slippage and PnL;
- close/continue decisions and actual trade lifecycle.

No compatibility endpoint may return `closed_trade_skeletons` or
`arbitration_evidence`. Those fields cross the service boundary and belong to
Research Service.

### 13.4 No per-bar HTTP rule

Research Service must not make one HTTP call per bar. It requests a coarse
managed replay for a logical trade/range, then performs execution locally over
that returned ordered policy artifact.

### 13.5 Acceptance

- managed phase/stop/take/runtime-exit policy matches frozen legacy fixtures;
- Research fill arbitration matches separately frozen execution fixtures;
- Strategy Engine never returns fills or PnL;
- Research Service never recalculates managed policy;
- effective-time semantics are explicit and deterministic.

## 14. Seam L — final `VariantResult`

Current:

```python
run_strategy_spec(...) -> VariantResult
```

Fields:

```text
variant
config_id
symbol
timeframe
strategy_spec
metrics
component_counters
trade_records
trade_management_events
```

Target:

- Strategy Engine does not expose `VariantResult` as core result;
- BBB assembles `VariantResult` from engine evaluation + BBB simulation/research analysis;
- compatibility managed replay may return trade skeletons, never final report payload;
- report schema remains BBB-owned.

This prevents strategy engine from acquiring research report responsibility.

## 15. Error mapping requirements

Common response envelope:

```json
{
  "error": "validation_failed",
  "message": "...",
  "request_id": "...",
  "details": {},
  "issues": []
}
```

Required codes:

```text
400 invalid_request
404 strategy_not_found
404 indicator_not_found
409 market_stream_not_ready
409 compatibility_profile_not_supported
422 validation_failed
422 range_not_aligned
422 range_out_of_bounds
422 unsupported_output_projection
500 evaluation_invariant_broken
503 market_data_unavailable
503 service_unavailable
```

BBB clients must map engine failures into current backtest/config/trace error contracts without exposing raw stack traces.

## 16. API compatibility invariants

- canonical ticker uses `.P` identity;
- ranges are milliseconds and half-open `[from_ms,to_ms)`;
- output arrays align exactly with `time_ms`;
- ordering is deterministic;
- feature/strategy version and config hash are explicit;
- warmup values are explicit `null`, not silently dropped;
- no frontend seconds or tooltip strings in core evaluation;
- no fills/fees/PnL in static evaluation;
- no hidden market reads inside domain methods;
- FastAPI routers contain no pandas/indicator/strategy logic;
- engine application does not import BBB contracts.

## 17. Audit completion checklist before first semantic OpenSpec

- [x] immutable raw copy and hashes;
- [x] top-level runner path;
- [x] validation seam;
- [x] feature-plan seam;
- [x] indicator calculation seam;
- [x] context seam;
- [x] entry seam;
- [x] static exit seam;
- [x] Workbench signal-trace seam;
- [x] component catalog seam;
- [x] managed provider/loop complication;
- [ ] verify every direct-port file in `06_bbb_source_inventory.csv` against this ownership map;
- [ ] verify every mixed file function by function;
- [ ] enumerate exact report/trace fields that depend on `ExitAttributionContext`;
- [ ] enumerate all accepted/rejected external config fixtures;
- [ ] define numeric parity tolerance per indicator;
- [ ] decide first OpenSpec exact scope and acceptance matrix.
