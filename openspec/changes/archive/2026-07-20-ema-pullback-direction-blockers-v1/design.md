# Design: EMA Pullback Direction and Blockers v1

## Current BBB seam

`build_signals_from_spec()` resolves the direction component, evaluates each blocker, applies any context gate to each blocker, AND-composes blockers, and later combines them with setup, trigger, and risk masks.

This change ends immediately before setup evaluation:

```text
FeatureFrame + ContextBundle + StrategySpec
→ direction mask
→ intrinsic blocker masks
→ per-blocker context gates
→ blockers_ok
→ pre_setup_allowed
```

## Module ownership

`strategies/ema_pullback/direction_blockers.py` owns pure strategy semantics. It consumes already calculated features and canonical market bars carried internally by `FeatureFrame`. It performs no HTTP, SQL, MDS call, indicator calculation, setup evaluation, or execution simulation.

## Ordering invariant

For each blocker:

```text
intrinsic blocker mask
AND optional context allowed mask
= final blocker mask
```

Then:

```text
AND(all final blocker masks) = blockers_ok

direction AND blockers_ok = pre_setup_allowed
```

## Supported components

- `ema_anchor_stack_trend`
- `no_blockers`
- `counter_candle_blocker`
- `rsi_lookback_extreme_blocker`
- `trend_strength_episode_blocker`

## Transport

The existing coarse-grained `POST /v1/strategy-evaluations/range` response adds `component_evidence.direction_blockers`. No new network endpoint is introduced.
