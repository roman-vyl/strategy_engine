# Design: EMA Pullback exit policy v1

## Pipeline

```text
FeatureFrame + canonical StrategySpec + context-consumption profiles
→ evaluate each exit rule once
→ compose always-on + profile-local signals/distances
→ select aligned/countertrend/neutral per side and bar
→ StrategyRangeResult.exit_policy
```

## Ownership boundary

Strategy Engine owns the policy decision: signal exit requested, stop/take distance required, selected profile, and readiness. BBB or the future runtime owns execution facts: fill price, hit ordering, fees, position state, and PnL.

## Compatibility rules

- Multiple signal rules combine with OR.
- Multiple stop-loss or take-profit distance rules combine using the smallest relative distance.
- ATR and constant-USD distances are converted to `distance / close`, matching BBB vectorbt-facing semantics.
- If no exit-policy context consumption exists, both sides use `neutral`.
- Disabled sides produce false signal masks and do not emit side-specific rule counters.
- Stop readiness matches BBB: a configured stop/take series must be non-null on the bar; an absent rule kind does not block readiness.

## API representation

Relative numeric distances are serialized as normalized decimal text or `null`. Boolean masks and selected profile/state arrays remain bar-aligned with the FeatureFrame time axis.
