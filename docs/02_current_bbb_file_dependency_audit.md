# Current BBB file and dependency audit

## Core finding

The final engine boundary is narrower than the physical first copy. `spec.py`, feature planning, component registries, context validation and managed policy are tightly connected. Copying only `features/` or only `components/` would immediately force ad-hoc duplicate contracts.

Therefore:

1. The first physical copy preserves the complete `research/strategies/ema_pullback` directory as an immutable porting reference.
2. Clean production modules are then built under `src/strategy_engine` by responsibility.
3. BBB is not modified during this phase.

## External dependencies that must not become engine ownership

| Current dependency | Used by | Target action |
|---|---|---|
| `data_engine.contracts.validate_timeframe` | `spec.py` | Replace with engine-owned timeframe contract aligned with Market Data Service. |
| `data_engine.contracts.pandas_freq_alias` | feature calculations/backtest | Indicator Engine owns only calculation aliasing; backtest usage stays BBB. |
| `data_engine.contracts.TimeWindow` | data loader | Do not port loader; engine API uses its own half-open range DTO. |
| `data_engine.store.Db` | data loader / BFF services | Replace with Market Data Service client adapter. |
| `vectorbt`, `numba` | backtest execution | Keep in BBB Research. |
| `research.experiments.*` | runner/config envelope | Keep experiment orchestration in BBB. |
| `research_api.*` | BFF contracts | Keep in BBB; add clients/adapters later. |

## Direct semantic-port candidates

These files have predominantly engine-owned responsibility and should become working code in the new repository after the raw copy.

### Strategy contracts and validation

- `research/strategies/ema_pullback/spec.py`
- `research/strategies/ema_pullback/component_builders.py`
- `research/strategies/ema_pullback/consumer_roles.py`
- `research/strategies/ema_pullback/instance_loader.py`
- `research/strategies/ema_pullback/spec_instances.py`

Target responsibilities:

- canonical strategy DTOs;
- config parsing/validation;
- component IDs and roles;
- deterministic config serialization/hash;
- strategy catalog schema.

`instance_loader.py` is large and should later be split into config sections, but the initial semantic port must preserve validation behavior before refactoring.

### Indicator Engine

- `research/strategies/ema_pullback/features/__init__.py`
- `research/strategies/ema_pullback/features/plan.py`
- `research/strategies/ema_pullback/features/calculations.py`

Target responsibilities:

- declarative feature planning;
- batch feature calculation;
- HTF resampling and completed-value alignment;
- warmup/validity metadata;
- stable feature IDs.

### Strategy components

- `research/strategies/ema_pullback/components/__init__.py`
- `components/registry.py`
- `components/direction.py`
- `components/blockers.py`
- `components/setup.py`
- `components/triggers.py`
- `components/exits.py`
- `components/risk.py`
- `components/context.py`
- `components/trend_strength_episode.py`

### Context semantics

- `context/__init__.py`
- `context/bundle.py`
- `context/evaluation.py`
- `context/pipeline.py`
- `context/policies.py`
- `context/consumption_validation.py`

`context/consumption_trace.py` is classified separately because it mixes semantic evidence with trace/report preparation.

### Entry/setup/exit evaluation

- `setup_runtime.py`
- `execution/signals.py`
- `execution/exits.py`
- `phase_rule_conditions/__init__.py`
- `phase_rule_conditions/params.py`
- `phase_rule_conditions/registry.py`

### Clearly strategy-owned managed components

- `execution/managed_components/__init__.py`
- `managed_components/activation.py`
- `managed_components/atr.py`
- `managed_components/runtime_exit.py`
- `managed_components/stop.py`
- `managed_components/take.py`

## Mixed-responsibility files that require splitting

These files must be present in the raw reference copy but must not be promoted wholesale into final engine core.

| Source file | Engine-owned part | BBB/caller-owned part |
|---|---|---|
| `execution/trade_runtime.py` | strategy phase state, managed policy evaluation, next strategy state | diagnostics aggregation, trade-record mutation, report summaries |
| `execution/managed_exit_provider.py` | policy facade from position/strategy state to decisions | coupling to current execution-loop objects |
| `execution/managed_bar_open_candidates.py` | managed protection/runtime-exit intent | bar fill candidate representation tied to simulator |
| `execution/managed_components/snapshot.py` | active policy snapshot | current trade-runtime/report DTO coupling |
| `execution/exit_policy_candidates.py` | mapping strategy exit policy to abstract decisions | OHLC hit/fill candidate construction |
| `execution/exit_attribution.py` | stable rule/component attribution | execution-fill attribution and trade-record helpers |
| `execution/signal_trace.py` | component evidence and event semantics | Workbench labels/tooltips/slicing/trace payload |
| `context/consumption_trace.py` | context-consumption evidence | trace-specific payload assembly |
| `spec_report.py` | possible canonical spec serialization compatibility | parsing legacy BBB report payloads |

Each mixed file requires characterization tests before splitting.

## Files that remain in BBB

### Research orchestration and market loading

- `cli.py`
- `run.py`
- `config.py`
- `execution/data_loader.py`
- `execution/runner.py`

### Backtest/execution simulation

- `execution/backtest.py`
- `execution/managed_execution_loop.py`
- `execution/exit_arbitration.py`

The seam is extracted from `backtest.py`, but the vectorbt and managed fill loops remain in BBB.

### Results, reports and analysis

- `execution/result_models.py`
- `execution/results.py`
- `execution/report_table.py`
- `execution/trade_analyzer.py`
- `execution/managed_comparison.py`
- `spec_report.py` legacy/report portions
- `execution/signal_trace.py` Workbench formatting portions

## Historical BBB callers represented by new service contracts

- `research/experiments/config_loader.py`
- `research/experiments/batch_runner.py`
- `research/experiments/validation.py`
- `research_api/services/backtest_service.py`
- `research_api/services/config_service.py`
- `research_api/services/component_catalog.py`
- `research_api/services/signal_trace_service.py`

## Required active parity-test groups

The raw snapshot contains many tests importing `ema_pullback`. The first active parity suite should prioritize:

### Indicator parity

- `tests/test_ema_pullback_features_atr.py`
- `tests/test_ema_pullback_feature_profile.py`
- `tests/test_htf_regime_gate.py`
- feature-related cases in `tests/test_ema_pullback_signal_trace.py`

### Component and entry/exit parity

- `tests/test_ema_pullback_components.py`
- `tests/test_ema_pullback_pipeline.py`
- `tests/test_ema_pullback_setup_stack.py`
- `tests/test_anchor_stack_width_setup.py`
- `tests/test_trend_strength_episode_blocker.py`
- `tests/test_ema_pullback_exits.py`
- `tests/test_ema_pullback_exit_ema_signals.py`
- `tests/test_strategy_level_contexts.py`
- `tests/test_setup_component_context_boundary.py`

### Managed-policy parity

- `tests/test_phase_rule_conditions.py`
- `tests/test_exit_management_contracts.py`
- `tests/test_managed_stop_components.py`
- `tests/test_managed_take_components.py`
- `tests/test_managed_runtime_exit_components.py`
- `tests/test_managed_exit_provider.py`
- `tests/test_runtime_reusable_signal_exits.py`

### BBB execution/report tests kept as downstream acceptance

Tests for vectorbt, results artifacts, research API, reports and diagnostics remain in BBB and later verify that API outputs produce equivalent downstream results.
