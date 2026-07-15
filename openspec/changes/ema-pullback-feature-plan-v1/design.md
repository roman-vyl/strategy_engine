# Design: EMA Pullback Feature Plan v1

## Current BBB seam

```text
EmaPullbackStrategySpec
→ build_feature_plan_from_strategy_spec(spec)
→ FeaturePlan
→ add_feature_columns_from_plan(...)
```

The new implementation accepts the canonical JSON representation produced by BBB `strategy_spec_to_dict`. It owns feature discovery and emits the new engine's `IndicatorPlan` plus BBB-compatible lookup mappings.

## API

```http
POST /v1/strategies/ema_pullback/feature-plan
```

The body is the existing `StrategySpecEnvelope` and therefore contains `strategy_id`, `strategy_version`, `instance_id`, `raw_spec`, and `compatibility_profile`.

The response contains:

- `plan_version` and deterministic `plan_hash`;
- ordered `features` using current Indicator Engine contracts;
- `anchor_columns`;
- `exit_distance_columns`;
- `rsi_columns`;
- `adx_dmi_columns`;
- `setup_columns_by_instance_id`;
- `ema_columns`;
- `htf_context_columns_by_ref`.

## Compatibility decisions

- Feature IDs preserve BBB names exactly.
- Duplicate requested features keep first-insertion order.
- ATR-distance dependencies point to the already planned ATR output.
- `ema_pullback` validation succeeds when feature planning succeeds, even though full strategy evaluation remains unsupported.
- `/v1/strategy-evaluations/range` continues to return `501 unsupported_capability`.
