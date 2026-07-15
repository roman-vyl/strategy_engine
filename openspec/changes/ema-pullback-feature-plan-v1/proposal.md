# Proposal: EMA Pullback Feature Plan v1

## Why

External callers should provide the strategy specification, market identity, and evaluation range. They must not reproduce BBB feature discovery or manually construct indicator plans. The first strategy-owned semantic slice therefore ports the exact BBB `EmaPullbackStrategySpec -> FeaturePlan` responsibility.

## Scope

- accept the canonical BBB serialized strategy spec (`strategy_spec_to_dict` shape);
- build an ordered, deduplicated IndicatorPlan;
- preserve BBB output identifiers and lookup mappings;
- advertise `ema_pullback` in the strategy catalog as feature-planning capable;
- expose a coarse-grained FastAPI feature-plan endpoint;
- keep full strategy range evaluation unsupported until contexts and decisions are ported.

## Out of scope

- external config instance loading;
- context evaluation;
- entry/exit evaluation;
- managed execution;
- BBB cutover;
- incremental runtime.
