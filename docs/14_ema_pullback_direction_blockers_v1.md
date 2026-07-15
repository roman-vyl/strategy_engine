# EMA Pullback direction and blockers v1

The Strategy Engine now evaluates the first local trading masks after feature/context preparation.

```text
FeatureFrame
+ ContextBundle
+ canonical StrategySpec
→ direction
→ blocker masks
→ context-gated blocker masks
→ blockers_ok
→ pre_setup_allowed
```

Supported blockers are `no_blockers`, `counter_candle_blocker`, `rsi_lookback_extreme_blocker`, and `trend_strength_episode_blocker`. The context gate is applied after intrinsic blocker logic, matching BBB. `pre_setup_allowed` is evidence only; setup, trigger, risk, and final entries remain unported.
