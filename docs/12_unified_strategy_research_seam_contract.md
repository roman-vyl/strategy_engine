# Unified BBB strategy/research seam contract

## Status

This document is normative for both `strategy_engine` and `research_service`.
It describes one physical cut through the same legacy BBB call graph. The two
new repositories are not independent reinterpretations of that graph:

```text
legacy BBB combined pipeline
  strategy semantics
  -------------------- API seam --------------------
  research execution and presentation
```

`legacy_source/bbb/` is a disconnected read-only mirror. Production code may
not import, load, execute or fall back to it.

## Authoritative ownership

### Strategy Engine owns

- strategy-spec normalization and semantic validation;
- feature-plan construction;
- indicator, context and component evaluation;
- entry decisions;
- initial stop/take policy;
- standard signal exits;
- managed phase, stop, take-profile and runtime-exit policy decisions;
- strategy evidence and semantic event identity.

### Research Service owns

- research-run orchestration;
- canonical OHLCV acquisition for simulation;
- entry and exit fill execution;
- gap/open handling and same-bar arbitration;
- position lifecycle;
- fees, slippage, PnL, equity and metrics;
- trade records, artifacts, diagnostics projection and Workbench DTOs.

## Shared legacy call map

| Legacy caller/file | Legacy callee or mixed responsibility | Strategy Engine replacement | Research Service consumer/replacement |
|---|---|---|---|
| `execution/runner.py::run_strategy_specs_from_config` | config load, market load, per-variant strategy run, result write | authoring validation and strategy range evaluation APIs | new run orchestration, MDS read, simulator, artifact writer |
| `execution/data_loader.py::load_candles_once` | local BBB market read | Strategy Engine reads its own calculation range through MDS | Research Service reads the execution range through `MarketDataPort` |
| `execution/backtest.py::run_strategy_spec` | feature plan, indicators, contexts, entries, exits, execution, metrics | `POST /v1/strategy-evaluations/range` | `RunResearchBacktest` consumes `StrategyEvaluationResult` and simulates fills/trades |
| `execution/managed_execution_loop.py::run_managed_execution_loop` | managed-policy evaluation plus OHLC execution | `POST /v1/strategy-evaluations/managed-replay` supplies policy state/events for an open logical trade | simulator applies policy candidates to OHLC, arbitrates hits, fills and closes positions |
| `managed_exit_provider.py::ManagedExitProvider.get_bar_open_candidates` | strategy-owned candidate policy presented at bar open | managed replay response, effective-time and candidate metadata | candidate adapter plus execution arbitration |
| `managed_exit_provider.py::ManagedExitProvider.update_end_of_bar_snapshot` | strategy-owned phase/stop/take/runtime-exit update | managed replay per-bar state and ordered events | simulator consumes next-effective state; it does not recalculate policy |
| `execution/signal_trace.py::build_signal_trace_from_spec` | semantic evidence plus Workbench labels/DTO | range evaluation evidence, contexts, component events and decisions | trace projector, slicing, labels/tooltips and public BFF contracts |
| `execution/results.py`, `result_models.py`, `trade_analyzer.py` | trade normalization, accounting, metrics, diagnostics and writing | no replacement; these are beyond the Strategy Engine boundary | rewritten accounting, result domain, diagnostics and artifact modules |

## Exact `run_strategy_spec` cut

The following legacy calls are replaced by one Strategy Engine coarse request:

```text
build_feature_plan_from_strategy_spec
add_feature_columns_from_plan
build_context_bundle_for_spec
strategy direction/blocker/setup/trigger evaluation
entry-mask construction
standard exit-policy construction
managed-policy decision construction
```

The new Research Service does not recreate adapters that masquerade as the old
BBB enriched DataFrame. It consumes a typed `StrategyEvaluationResult` directly.

```text
StrategyEnginePort.evaluate_strategy_range(...)
  -> StrategyEvaluationResult
MarketDataPort.get_candles(...)
  -> MarketFrame
RunResearchBacktest(...)
  -> BacktestResult
```

## Exact managed-loop cut

For each bar, the ownership order is:

```text
Strategy Engine policy artifact effective for this bar
+ current Research position state
+ canonical OHLC bar
  -> Research candidate-hit detection
  -> deterministic same-bar arbitration
  -> fill price / fees / PnL / close or continue
  -> next Strategy Engine policy artifact is consumed when effective
```

Strategy Engine does not return fills, closed-trade skeletons or arbitration
results. Research Service does not calculate phase transitions, managed stop
levels, take-profile switching or runtime-exit activation.

The authoritative managed endpoint is:

```http
POST /v1/strategy-evaluations/managed-replay
```

No separate compatibility managed-execution endpoint is part of the target
architecture.

## Exact signal-trace cut

Strategy Engine returns semantic data:

- ordered timestamps;
- component IDs, roles, sides and instance IDs;
- masks, state values, evidence and raw metadata;
- context and context-consumption state;
- entry, exit and managed-policy events.

Research Service returns presentation data:

- run/variant/window slicing;
- Unix-seconds chart conversion;
- labels, tooltips and Workbench DTOs;
- artifact lookup and BFF caching.

## Alignment invariant

Before simulation, Research Service must reject any mismatch between the
Strategy Engine decision frame and the MDS execution frame:

- ticker;
- timeframe;
- requested evaluation range;
- ordered timestamps and bar count;
- market-data identity/hash when available.

No local indicator recalculation, interpolation, silent truncation or legacy
fallback is permitted.
