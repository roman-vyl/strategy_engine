# Design: EMA Pullback Triggers v1

## Pipeline position

```text
pre_trigger_allowed
→ trigger local semantics
→ trigger_ok
→ pre_risk_entry_allowed
```

## Components

### reclaim_anchor

For long, a prior candle in the configured lookback must wick-probe `low <= anchor`, while the current close must reclaim `close > anchor`. Short mirrors the inequalities. The current candle's probe is excluded because the rolling probe window is shifted by one bar.

### strong_reclaim_anchor

The same prior-window rule applies, but the probe uses prior close rather than wick range.

### touch_anchor

The current candle must touch the anchor and close on the permitted side. It has no lookback.

## Composition

```text
pre_risk_entry_allowed = pre_trigger_allowed AND trigger_ok
```

No context gate is applied directly to triggers in the current BBB contract. Direction, blocker, and setup context policies have already been applied upstream.

## API result

`POST /v1/strategy-evaluations/range` adds `component_evidence.triggers` with the exact trace fields used by BBB and reports stage `triggers_ready`. `entries` remains empty and `decisions_ready` remains false until risk is ported.
