# Current BBB call and data-contract audit

## Audit source

- Snapshot: `project_snapshot_20260711.zip`
- SHA-256: `3020cf491a185e495c16b77caddb9e8c06acb7e6577d6b6d9fe5efc9373046e6`
- Strategy package: `research/strategies/ema_pullback`
- Package size: 61 files, 60 Python files, approximately 15,615 lines.

## Current top-level callers

### CLI / direct research run

```text
research/strategies/ema_pullback/run.py
  -> execution/runner.py::run_strategy_specs_from_config
  -> research/experiments/config_loader.py::load_strategy_config_file
  -> instance_loader.py::load_ema_pullback_config_entry
  -> execution/data_loader.py
  -> execution/backtest.py::run_strategy_spec
```

### Experiment batch runner

```text
research/experiments/batch_runner.py
  -> execution/runner.py::run_strategy_specs_from_config_returning_paths
  -> the same runner/data-loader/backtest path
```

### Research API backtest

```text
research_api/services/backtest_service.py
  -> execution/runner.py::run_strategy_specs_from_config
```

### Workbench signal trace

Workbench trace does **not** reuse a saved strategy-evaluation artifact. It recomputes a parallel path:

```text
research_api/services/signal_trace_service.py
  -> reconstruct StrategySpec from report
  -> load OHLCV directly from legacy Db
  -> build_feature_plan_from_strategy_spec
  -> add_feature_columns_from_plan
  -> build_signal_trace_from_spec
  -> convert to Workbench contracts
```

This is an important duplication seam: indicator and component evaluation are recalculated outside the original backtest run.

### Composer/catalog/config

- `research_api/services/component_catalog.py` owns a BBB-side component catalog.
- `research_api/services/config_service.py` and `research/experiments/config_loader.py` validate/load BBB strategy configs.
- `instance_loader.py` contains the authoritative detailed `ema_pullback` parsing and validation today.

The target engine must eventually become authoritative for strategy and indicator schemas; BBB should retain a BFF adapter, not a second semantic catalog.

## Natural seam inside `run_strategy_spec`

`research/strategies/ema_pullback/execution/backtest.py::run_strategy_spec` currently executes:

```python
plan = build_feature_plan_from_strategy_spec(spec)
enriched = add_feature_columns_from_plan(ohlcv, plan)
context_bundle = build_context_bundle_for_spec(spec, enriched, plan)
signals = build_signals_from_spec(enriched, spec, plan, context_bundle=context_bundle)
exit_outputs = build_exit_outputs_from_spec(enriched, spec, plan, context_bundle=context_bundle)
```

After those calls the function branches into:

- vectorbt portfolio execution;
- managed execution loop;
- fill and stop/take arbitration;
- trade extraction;
- fees, PnL and metrics;
- diagnostics and report artifacts.

Therefore the primary extraction seam is:

```text
StrategySpec + canonical OHLCV
  -> FeaturePlan
  -> FeatureFrame
  -> ContextBundle
  -> Entry/Exit/Protection decisions
-------------------------------------------- seam
  -> execution simulation / exchange execution
  -> trades / PnL / reports / Workbench artifacts
```

## Current inputs

The combined BBB pipeline currently receives:

- parsed `EmaPullbackStrategySpec`;
- base-timeframe OHLCV DataFrame;
- feature requirements derived from the strategy spec;
- optional HTF requirements, calculated by feature resampling/alignment;
- execution economics: initial cash, fees and slippage;
- managed-exit path state derived from simulated open trades.

## Current intermediate contracts

### `FeaturePlan`

Defined in `features/plan.py`. It contains:

- planned feature definitions;
- anchor EMA column mapping;
- exit-distance columns;
- RSI and ADX/DMI mappings;
- setup-specific columns;
- HTF context columns.

### Enriched OHLCV DataFrame

Produced by `features/calculations.py::add_feature_columns_from_plan`.

It preserves OHLCV and appends named feature columns. Current calculation code owns:

- EMA;
- ATR and ATR-distance;
- RSI;
- ADX, DI+ and DI-;
- HTF resampling;
- completed-HTF-value alignment back to the base timeframe.

### `ContextBundle`

Produced by `context/pipeline.py::build_context_bundle_for_spec`. It resolves strategy-level context providers from feature columns.

### `PortfolioSignals`

Produced by `execution/signals.py::build_signals_from_spec`. It includes long and short entries, component counters, blocker/setup masks and context-consumption results.

### `PortfolioExitOutputs`

Produced by `execution/exits.py::build_exit_outputs_from_spec`. It includes:

- profile-aware signal exits;
- stop/take ratio series;
- stop readiness;
- exit attribution data;
- context/profile outputs.

These names are BBB implementation names, not necessarily final public API DTO names. Their semantics must be preserved by parity fixtures.

## Current final outputs

`run_strategy_spec` returns `VariantResult`, which mixes several layers:

- strategy identity/config;
- component counters;
- simulated trade records;
- metrics;
- managed trade events;
- report-oriented summaries.

The new Strategy Engine must not return `VariantResult` as its core result. It should return strategy decisions/evidence; BBB continues to construct `VariantResult` from simulation results.

## Managed-exit complication

The simple seam “signals out, trades stay in BBB” is insufficient for managed exits.

Current code splits managed behavior across:

- `execution/managed_exit_provider.py`;
- `execution/managed_bar_open_candidates.py`;
- `execution/managed_components/*`;
- `execution/trade_runtime.py`;
- `execution/exit_policy_candidates.py`;
- `execution/exit_arbitration.py`;
- `execution/managed_execution_loop.py`.

The future split must be:

```text
Strategy Engine owns policy:
  phase transitions, activation, managed stop/take/runtime-exit decisions

Caller owns execution facts:
  actual/simulated position, fills, same-bar arbitration, fees and PnL
```

Several current files mix those responsibilities and require semantic splitting rather than whole-file promotion into final core.

## Current frontend compatibility boundary

Workbench should continue to call BBB `research_api`. The migration path is:

```text
Workbench
  -> unchanged BBB BFF endpoints
  -> new IndicatorEngineClient / StrategyEngineClient
  -> independent engine APIs
```

BBB remains responsible for:

- chart seconds versus backend milliseconds;
- Workbench DTOs;
- coverage and viewport-specific formatting;
- report/trace aggregation;
- converting engine evidence into existing component-event and trace contracts.


## Normative cross-service seam

The exact two-sided cut between Strategy Engine and Research Service is defined in `docs/12_unified_strategy_research_seam_contract.md`.
