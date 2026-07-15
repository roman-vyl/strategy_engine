# EMA Pullback Feature Plan v1

## Purpose

This slice moves the first strategy-owned responsibility out of BBB: discovering all indicator features required by a canonical `ema_pullback` strategy specification.

## Input

The application boundary accepts `StrategySpecEnvelope` with:

- `strategy_id=ema_pullback`;
- `strategy_version=v1`;
- `instance_id`;
- `compatibility_profile=bbb_v1`;
- `raw_spec` in BBB `strategy_spec_to_dict` shape.

## Internal result

`EmaPullbackFeaturePlan` contains:

- the new Indicator Engine `IndicatorPlan`;
- anchor-stack column mapping;
- context column mappings;
- setup-specific mappings;
- exit ATR-distance mappings;
- RSI, EMA and ADX/DMI lookup mappings.

Feature IDs, order and deduplication match the copied BBB `build_feature_plan_from_strategy_spec` implementation.

## HTTP boundary

```http
POST /v1/strategies/ema_pullback/feature-plan
```

The caller supplies only the strategy envelope. The engine discovers EMA, ATR, ATR-distance, RSI and ADX/DMI requirements internally.

## Capability status

The strategy catalog advertises:

```text
supports_feature_planning = true
supports_range_evaluation = false
supports_incremental = false
```

`POST /v1/strategy-evaluations/range` therefore continues to return `501 unsupported_capability`. This prevents a partial feature-only result from being mistaken for a completed strategy evaluation.

## Deferred work

- external BBB config-instance loader;
- context evaluation;
- direction/blocker/setup/trigger evaluation;
- exit-policy evaluation;
- managed policy;
- BBB API consumer cutover;
- bar-to-bar runtime.
