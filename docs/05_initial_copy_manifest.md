# Initial physical copy manifest

## Copy rule

The first source copy is an immutable evidence snapshot. It is not the clean engine package and does not need to import successfully.

## Exact primary source directory

Copy recursively, without exclusions:

```text
BBB source:
  research/strategies/ema_pullback/

New repository target:
  legacy_source/bbb/research/strategies/ema_pullback/
```

Snapshot count at audit time:

- 61 files total;
- 60 Python files;
- approximately 15,615 lines of Python.

## Exact selected helper files

Copy as reference because direct semantic tests use them:

```text
tests/ema_pullback_context_helpers.py
tests/phase_rule_test_helpers.py
```

## Exact active parity-test seed list

Copy to `legacy_source/bbb/tests/` first; later port assertions/fixtures into the clean test suite.

```text
tests/test_anchor_stack_width_setup.py
tests/test_consumer_roles.py
tests/test_ema_pullback_components.py
tests/test_ema_pullback_exit_ema_signals.py
tests/test_ema_pullback_exits.py
tests/test_ema_pullback_feature_profile.py
tests/test_ema_pullback_features_atr.py
tests/test_ema_pullback_pipeline.py
tests/test_ema_pullback_setup_stack.py
tests/test_exit_attribution.py
tests/test_exit_management_contracts.py
tests/test_htf_regime_gate.py
tests/test_managed_exit_provider.py
tests/test_managed_runtime_exit_components.py
tests/test_managed_stop_components.py
tests/test_managed_take_components.py
tests/test_phase_rule_conditions.py
tests/test_runtime_reusable_signal_exits.py
tests/test_setup_component_context_boundary.py
tests/test_strategy_level_contexts.py
tests/test_trend_strength_episode_blocker.py
```

## Downstream BBB acceptance tests — do not activate in the new repository initially

Keep these in BBB as cutover acceptance because they test simulation, reports or BFF behavior:

```text
tests/test_ema_pullback_results_artifact.py
tests/test_ema_pullback_run_metrics.py
tests/test_ema_pullback_trade_analyzer.py
tests/test_experiment_batch_runner.py
tests/test_experiment_models.py
tests/test_external_config_loader.py
tests/test_managed_comparison.py
tests/test_managed_execution_integration.py
tests/test_managed_report_contract.py
tests/test_research_api_chart_events.py
tests/test_research_api_run_report.py
tests/test_research_api_runs.py
tests/test_research_api_signal_trace.py
tests/test_trade_path_diagnostics.py
tests/test_trade_runtime_diagnostics.py
tests/test_trade_runtime_managed_core.py
```

## Do not copy as engine dependencies

Do not copy these packages to make the raw slice run:

```text
data_engine/
research/experiments/
research_api/
frontend/
research/results/
```

Their required contracts must be replaced by explicit engine ports/API clients.

## First clean working-port mapping

| BBB source | Clean target |
|---|---|
| `spec.py` | `src/strategy_engine/strategies/ema_pullback/spec.py` |
| `instance_loader.py` | `src/strategy_engine/strategies/ema_pullback/config/loader.py` |
| `component_builders.py` | `src/strategy_engine/strategies/ema_pullback/config/builders.py` |
| `consumer_roles.py` | `src/strategy_engine/strategies/contracts/consumer_roles.py` |
| `features/plan.py` | `src/strategy_engine/indicators/planning.py` |
| `features/calculations.py` | `src/strategy_engine/indicators/batch/calculations.py` plus resampling/alignment modules |
| `components/*` | `src/strategy_engine/strategies/ema_pullback/components/*` |
| `context/*` semantic files | `src/strategy_engine/strategies/ema_pullback/context/*` |
| `setup_runtime.py` | `src/strategy_engine/strategies/ema_pullback/evaluation/setups.py` |
| `execution/signals.py` | `src/strategy_engine/strategies/ema_pullback/evaluation/entries.py` |
| `execution/exits.py` | `src/strategy_engine/strategies/ema_pullback/evaluation/exits.py` |
| `phase_rule_conditions/*` | `src/strategy_engine/strategies/ema_pullback/managed/phase_conditions/*` |
| pure managed components | `src/strategy_engine/strategies/ema_pullback/managed/components/*` |

Mixed files are not assigned a one-to-one clean target until characterization tests define the split.

## First next command after approval

The next implementation step should create a deterministic copy script driven by this manifest, perform the raw copy, and record file hashes. It should not yet edit imports or attempt to make the copied package runnable.
